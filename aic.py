#!/home/chocotonilitz/scripts/venv/bin/python
import os
import subprocess
import requests
import sys
import argparse
import logging
import re
import time
from typing import Optional, List, Dict, Tuple, Any
from datetime import datetime
from functools import lru_cache

# ==========================================
# CONFIGURAÇÕES GERAIS
# ==========================================
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
MAX_COMMIT_LENGTH = 200
REQUEST_TIMEOUT = 6
LARGE_DIFF_THRESHOLD = 100
VERY_LARGE_DIFF_THRESHOLD = 300

# Cores para terminal
class Colors:
    INFO = '\033[0;34m'
    SUCCESS = '\033[0;32m'
    WARNING = '\033[0;33m'
    ERROR = '\033[0;31m'
    HIGHLIGHT = '\033[1;37m'
    RESET = '\033[0m'
    GRAY = '\033[0;90m'

# ==========================================
# FUNÇÕES DE UTILIDADE E GIT
# ==========================================
def create_commit_pattern_file():
    """Cria o arquivo commit_pattern.md com as regras padrão."""
    pattern_content = """# Commit Rules
1. Language: English (EN-US).
2. Length: Maximum of 1 line. Be direct and concise.
3. Format: <type>(<scope>): <subject>
4. Allowed Types:
   - `feat`: A new feature
   - `fix`: A bug fix
   - `docs`: Documentation only changes
   - `style`: Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc)
   - `refactor`: A code change that neither fixes a bug nor adds a feature
   - `perf`: A code change that improves performance
   - `test`: Adding missing tests or correcting existing tests
   - `chore`: Changes to the build process or auxiliary tools and libraries
5. Suggested Scopes: api, ui, db, auth, config, core.
6. Practice: Use the imperative, present tense: "change" not "changed" nor "changes". Don't capitalize the first letter. No dot (.) at the end.

Ideal Example: feat(api): add user authentication endpoint
Bad Example: feat(api): I added a new user authentication endpoint to the system"""
    
    if not os.path.exists("commit_pattern.md"):
        with open("commit_pattern.md", "w", encoding="utf-8") as f:
            f.write(pattern_content)
        logging.info("commit_pattern.md created successfully.")

def ensure_gitignore():
    """Verifica e adiciona os arquivos de padrão ao .gitignore automaticamente."""
    if not os.path.exists(".git"):
        return

    patterns_to_ignore = ["commit_pattern.md", "commit_pattern_pt.md"]
    gitignore_path = ".gitignore"
    
    content = ""
    if os.path.isfile(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()

    missing = [p for p in patterns_to_ignore if p not in content]
    
    if missing:
        with open(gitignore_path, "a", encoding="utf-8") as f:
            if content and not content.endswith("\n"):
                f.write("\n")
            f.write("\n# Ignorado automaticamente pelo CLI AI Commit\n")
            for m in missing:
                f.write(f"{m}\n")
        logging.info("Padrões de commit adicionados ao .gitignore automaticamente.")

def sanitize_diff(diff_text: str) -> str:
    """Varre o diff e oculta valores de chaves sensíveis."""
    regex = re.compile(r'(?i)(password|token|api_key|secret)(\s*[:=>]\s*)([\'"].*?[\'"]|[^\s\n\r,;]+)')
    return regex.sub(r'\1\2[REDACTED]', diff_text)

def count_diff_lines(diff_text: str) -> int:
    """Conta o número de linhas relevantes no diff"""
    if not diff_text:
        return 0
    return len([l for l in diff_text.splitlines() if l.startswith(('+', '-')) and not l.startswith(('+++', '---'))])

def determine_commit_type(key_additions: List[Dict], key_deletions: List[Dict], total_additions: int, total_deletions: int) -> str:
    """
    Determina o tipo de commit baseado na análise das mudanças:
    - feat: Muitas adições, poucas remoções (novas funcionalidades)
    - fix: Adições e remoções equilibradas (correção de bugs)
    - refactor: Muitas remoções, algumas adições (reescrita/refatoração)
    """
    add_count = len(key_additions)
    del_count = len(key_deletions)
    
    # Se há muitas adições de funções/classes novas
    new_features = [a for a in key_additions if a['type'] in ['function', 'async_function', 'class']]
    
    if len(new_features) >= 2 and total_additions > total_deletions * 2:
        return 'feat'
    
    # Se há equilíbrio entre adições e remoções (proporção ~1:1 a 1:2)
    if add_count > 0 and del_count > 0:
        ratio = add_count / del_count if del_count > 0 else float('inf')
        if 0.5 <= ratio <= 2.0:
            return 'fix'
    
    # Se há muitas remoções (refatoração)
    if del_count > add_count * 1.5 and total_deletions > 10:
        return 'refactor'
    
    # Se há adições de configuração
    if any(a['type'] == 'config' for a in key_additions):
        return 'chore'
    
    # Se há mudanças de performance
    perf_keywords = ['perf', 'performance', 'optimiz', 'fast', 'speed']
    if any(any(kw in a['line'].lower() for kw in perf_keywords) for a in key_additions + key_deletions):
        return 'perf'
    
    return 'refactor'  # default

def generate_diff_summary(diff_text: str) -> Dict[str, Any]:
    """
    Gera um resumo DETALHADO das mudanças reais no diff
    Extrai funções, classes, métodos e configurações adicionadas/removidas
    """
    lines = diff_text.splitlines()
    
    summary = {
        'files': {},
        'total_additions': 0,
        'total_deletions': 0,
        'key_additions': [],  # Funções/classes adicionadas
        'key_deletions': [],  # Funções/classes removidas
        'file_samples': {},   # Amostras de código por arquivo
        'main_purpose': '',
        'suggested_type': 'refactor',
        'suggested_scope': 'core'
    }
    
    current_file = None
    file_additions = 0
    file_deletions = 0
    
    # Padrões para identificar mudanças significativas
    patterns = {
        'function': re.compile(r'^\s*def\s+(\w+)'),
        'async_function': re.compile(r'^\s*async\s+def\s+(\w+)'),
        'class': re.compile(r'^\s*class\s+(\w+)'),
        'method': re.compile(r'^\s+def\s+(\w+)'),  # métodos indentados
        'decorator': re.compile(r'^\s*@(\w+)'),
        'import': re.compile(r'^\s*(?:from|import)\s+(\w+)'),
        'config': re.compile(r'^\s*([A-Z_][A-Z0-9_]*)\s*='),  # CONSTANTES
        'variable': re.compile(r'^\s*([a-z_][a-z0-9_]*)\s*='),  # variáveis
    }
    
    for line in lines:
        # Detecta mudança de arquivo
        if line.startswith('+++ b/'):
            if current_file:
                summary['files'][current_file] = {
                    'additions': file_additions,
                    'deletions': file_deletions
                }
            current_file = line[6:]  # Remove '+++ b/'
            file_additions = 0
            file_deletions = 0
            if current_file not in summary['file_samples']:
                summary['file_samples'][current_file] = {'additions': [], 'deletions': []}
        
        # Linha ADICIONADA
        elif line.startswith('+') and not line.startswith('+++'):
            summary['total_additions'] += 1
            file_additions += 1
            content = line[1:].rstrip()
            
            # Ignora linhas muito longas ou comentários
            if len(content) > 100 or content.strip().startswith(('#', '//', '/*', '*', '"""', "'''")):
                continue
            
            # Guarda amostra do código adicionado
            if current_file and len(summary['file_samples'][current_file]['additions']) < 10:
                sample = content[:60] + '...' if len(content) > 60 else content
                summary['file_samples'][current_file]['additions'].append(sample)
            
            # Detecta se é uma adição significativa
            for key, pattern in patterns.items():
                match = pattern.search(content)
                if match:
                    summary['key_additions'].append({
                        'file': current_file,
                        'type': key,
                        'name': match.group(1),
                        'line': content[:60] + '...' if len(content) > 60 else content
                    })
                    break
        
        # Linha REMOVIDA
        elif line.startswith('-') and not line.startswith('---'):
            summary['total_deletions'] += 1
            file_deletions += 1
            content = line[1:].rstrip()
            
            # Ignora linhas muito longas ou comentários
            if len(content) > 100 or content.strip().startswith(('#', '//', '/*', '*', '"""', "'''")):
                continue
            
            # Guarda amostra do código removido
            if current_file and len(summary['file_samples'][current_file]['deletions']) < 5:
                sample = content[:60] + '...' if len(content) > 60 else content
                summary['file_samples'][current_file]['deletions'].append(sample)
            
            # Detecta se é uma remoção significativa
            for key, pattern in patterns.items():
                match = pattern.search(content)
                if match:
                    summary['key_deletions'].append({
                        'file': current_file,
                        'type': key,
                        'name': match.group(1),
                        'line': content[:60] + '...' if len(content) > 60 else content
                    })
                    break
    
    # Não esquece do último arquivo
    if current_file:
        summary['files'][current_file] = {
            'additions': file_additions,
            'deletions': file_deletions
        }
    
    # Determina o tipo de commit baseado nas mudanças
    summary['suggested_type'] = determine_commit_type(
        summary['key_additions'],
        summary['key_deletions'],
        summary['total_additions'],
        summary['total_deletions']
    )
    
    # Determina o scope baseado nos arquivos modificados
    if current_file:
        file_lower = current_file.lower()
        if 'api' in file_lower or 'endpoint' in file_lower:
            summary['suggested_scope'] = 'api'
        elif 'ui' in file_lower or 'view' in file_lower or 'template' in file_lower:
            summary['suggested_scope'] = 'ui'
        elif 'db' in file_lower or 'database' in file_lower or 'model' in file_lower:
            summary['suggested_scope'] = 'db'
        elif 'auth' in file_lower or 'login' in file_lower or 'user' in file_lower:
            summary['suggested_scope'] = 'auth'
        elif 'config' in file_lower or 'setting' in file_lower:
            summary['suggested_scope'] = 'config'
        elif 'test' in file_lower:
            summary['suggested_scope'] = 'test'
        else:
            # Pega o nome base do arquivo (sem extensão)
            base = os.path.splitext(os.path.basename(current_file))[0]
            summary['suggested_scope'] = base
    
    return summary

def format_diff_for_prompt(diff_text: str, diff_size: int) -> str:
    """Formata o diff como um resumo LEGÍVEL para a IA"""
    
    summary = generate_diff_summary(diff_text)
    
    output = []
    output.append(f"📊 STATS: +{summary['total_additions']} -{summary['total_deletions']} in {len(summary['files'])} files")
    output.append("")
    
    # Lista arquivos modificados
    if summary['files']:
        output.append("📁 FILES MODIFIED:")
        for file, stats in list(summary['files'].items())[:5]:  # Top 5 arquivos
            output.append(f"  • {file} (+{stats['additions']} -{stats['deletions']})")
        if len(summary['files']) > 5:
            output.append(f"  • ... and {len(summary['files']) - 5} more")
        output.append("")
    
    # Mostra adições significativas (funções/classes novas)
    if summary['key_additions']:
        output.append("✨ NEW ADDITIONS:")
        for add in summary['key_additions'][:8]:  # Top 8
            output.append(f"  • {add['file']}: added {add['type']} `{add['name']}`")
        if len(summary['key_additions']) > 8:
            output.append(f"  • ... and {len(summary['key_additions']) - 8} more")
        output.append("")
    
    # Mostra remoções significativas
    if summary['key_deletions']:
        output.append("🗑️ REMOVALS:")
        for rem in summary['key_deletions'][:5]:  # Top 5
            output.append(f"  • {rem['file']}: removed {rem['type']} `{rem['name']}`")
        if len(summary['key_deletions']) > 5:
            output.append(f"  • ... and {len(summary['key_deletions']) - 5} more")
        output.append("")
    
    # Amostras de código (apenas para diffs médios)
    if diff_size <= VERY_LARGE_DIFF_THRESHOLD:
        output.append("📝 CODE SAMPLES:")
        samples_shown = 0
        for file, samples in summary['file_samples'].items():
            if samples['additions'] and samples_shown < 5:
                output.append(f"  In {file}:")
                for sample in samples['additions'][:3]:
                    output.append(f"    + {sample}")
                samples_shown += 1
        output.append("")
    
    # Sugestão baseada na análise
    output.append(f"💡 SUGGESTED: {summary['suggested_type']}({summary['suggested_scope']}): <description>")
    
    return "\n".join(output)

def get_git_diff(force: bool = False) -> Optional[Tuple[str, int]]:
    """Retorna diff processado e número de linhas"""
    start_time = time.time()
    
    if hasattr(get_git_diff, "cache"):
        cache_time, cache_diff, cache_lines = get_git_diff.cache
        if time.time() - cache_time < 2:
            logging.debug("Usando diff do cache")
            return cache_diff, cache_lines
    
    try:
        cmd = [
            "git", "diff", "--cached", 
            "--", ".", 
            ":(exclude).env", 
            ":(exclude)*.env.*"
        ]
        raw_diff = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode("utf-8")
        
        if not raw_diff.strip():
            logging.warning("Nenhuma alteração no stage. Use 'git add' primeiro.")
            return None, 0
        
        # Conta linhas relevantes
        diff_lines = count_diff_lines(raw_diff)
        
        # Se for muito grande e não estiver em modo force, pergunta
        if diff_lines > LARGE_DIFF_THRESHOLD and not force:
            print(f"{Colors.WARNING}⚠️  Large diff detected: {diff_lines} lines changed{Colors.RESET}")
            print(f"{Colors.INFO}This may slow down processing{Colors.RESET}")
            response = input(f"{Colors.INFO}Continue? (y/N): {Colors.RESET}").strip().lower()
            if response != 'y':
                print(f"{Colors.WARNING}Operation cancelled{Colors.RESET}")
                return None, 0
        
        # Formata diff baseado no tamanho
        formatted_diff = format_diff_for_prompt(raw_diff, diff_lines)
        formatted_diff = sanitize_diff(formatted_diff)
        
        if not formatted_diff:
            formatted_diff = "Modified files (content hidden for security)"
        
        # Guarda no cache
        get_git_diff.cache = (time.time(), formatted_diff, diff_lines)
        
        elapsed = (time.time() - start_time) * 1000
        original_size = len(raw_diff)
        new_size = len(formatted_diff)
        reduction = ((original_size - new_size) / original_size * 100) if original_size > 0 else 0
        
        logging.debug(f"Diff processed in {elapsed:.1f}ms")
        logging.debug(f"Reduction: {original_size} → {new_size} chars ({reduction:.1f}% smaller)")
        
        return formatted_diff, diff_lines
        
    except subprocess.CalledProcessError as e:
        logging.error("Git command failed. Verify this is a valid repository.")
        logging.debug(f"Details: {e.output.decode('utf-8')}")
        return None, 0
    except FileNotFoundError:
        logging.error("Git command not found.")
        return None, 0

# ==========================================
# CLIENTES DE API
# ==========================================
class GroqClient:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.url = "https://api.groq.com/openai/v1/chat/completions"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })

    def generate_commit(self, prompt: str, diff_size: int) -> Optional[str]:
        # Diffs grandes precisam de mais tokens
        max_tokens = 100 if diff_size > LARGE_DIFF_THRESHOLD else 60
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a strict Git commit message generator. Follow the format EXACTLY as specified. Return ONLY the commit message."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }

        try:
            response = self.session.post(self.url, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            return data['choices'][0]['message']['content'].strip()
        except Exception as e:
            logging.debug(f"Groq error: {e}")
            return None


class DeepSeekClient:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.url = "https://api.deepseek.com/v1/chat/completions"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })

    def generate_commit(self, prompt: str, diff_size: int) -> Optional[str]:
        max_tokens = 100 if diff_size > LARGE_DIFF_THRESHOLD else 60
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a strict Git commit message generator. Follow the format EXACTLY as specified. Return ONLY the commit message."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }

        try:
            response = self.session.post(self.url, json=payload, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            return data['choices'][0]['message']['content'].strip()
        except Exception as e:
            logging.debug(f"DeepSeek error: {e}")
            return None


class AIClient:
    def __init__(self):
        self.providers = []
        self.stats = {}
        
        # DeepSeek (rápido, médio contexto) - PRIORIDADE #1
        deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        if deepseek_key:
            self.providers.append({
                'name': 'DEEPSEEK',
                'priority_small': 1,
                'priority_large': 1,  # DeepSeek é bom para todos os tamanhos
                'client': DeepSeekClient(deepseek_key, DEFAULT_DEEPSEEK_MODEL)
            })
            self.stats['DEEPSEEK'] = {'avg_time': 0, 'success': 0, 'fails': 0}
        
        # Groq (mais rápido, contexto médio) - PRIORIDADE #2
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            self.providers.append({
                'name': 'GROQ',
                'priority_small': 2,
                'priority_large': 2,
                'client': GroqClient(groq_key, os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL))
            })
            self.stats['GROQ'] = {'avg_time': 0, 'success': 0, 'fails': 0}
        
        # Ordena por prioridade
        self.providers.sort(key=lambda x: x['priority_small'])
    
    def generate(self, prompt: str, diff_size: int, provider_override: str = None) -> Tuple[Optional[str], str, float]:
        """Gera commit escolhendo o provider baseado no tamanho do diff"""
        
        if provider_override:
            provider_override = provider_override.upper()
            for p in self.providers:
                if p['name'] == provider_override:
                    start = time.time()
                    result = p['client'].generate_commit(prompt, diff_size)
                    elapsed = time.time() - start
                    
                    if result:
                        self._update_stats(p['name'], elapsed, True)
                        return result, p['name'], elapsed
                    else:
                        self._update_stats(p['name'], elapsed, False)
                        return None, p['name'], elapsed
            return None, provider_override, 0
        
        # Escolhe prioridade baseada no tamanho
        is_large = diff_size > LARGE_DIFF_THRESHOLD
        providers_sorted = sorted(
            self.providers, 
            key=lambda x: x['priority_large' if is_large else 'priority_small']
        )
        
        for provider in providers_sorted:
            start = time.time()
            result = provider['client'].generate_commit(prompt, diff_size)
            elapsed = time.time() - start
            
            if result:
                self._update_stats(provider['name'], elapsed, True)
                return result, provider['name'], elapsed
            else:
                self._update_stats(provider['name'], elapsed, False)
                logging.debug(f"{provider['name']} failed in {elapsed:.2f}s")
        
        return None, "NONE", 0
    
    def _update_stats(self, provider: str, elapsed: float, success: bool):
        """Atualiza estatísticas de performance"""
        if provider not in self.stats:
            self.stats[provider] = {'avg_time': 0, 'success': 0, 'fails': 0}
        
        if success:
            self.stats[provider]['success'] += 1
            total = self.stats[provider]['success']
            self.stats[provider]['avg_time'] = (self.stats[provider]['avg_time'] * (total-1) + elapsed) / total
        else:
            self.stats[provider]['fails'] += 1


def build_optimized_prompt(pattern: str, diff: str, diff_size: int, suggested_type: str = None, suggested_scope: str = None, retry_count: int = 0) -> str:
    """Prompt adaptativo baseado no tamanho do diff"""
    
    types = re.findall(r'`(\w+)`:', pattern)
    scopes = re.findall(r'scopes:?\s*(.+?)(?:\n|$)', pattern, re.IGNORECASE)
    
    types_str = ', '.join(types[:10]) if types else 'feat, fix, docs, style, refactor, perf, test, chore'
    scopes_str = scopes[0] if scopes else 'api, ui, db, auth, config, core'
    
    # Extrai sugestão do resumo se disponível
    type_hint = f" (suggested: {suggested_type})" if suggested_type else ""
    scope_hint = f" (suggested: {suggested_scope})" if suggested_scope else ""
    
    if diff_size > LARGE_DIFF_THRESHOLD:
        # Para diffs grandes, usa o resumo detalhado
        prompt = f"""Generate a Git commit message for these changes:

{diff}

Based on the changes above, create a commit message in the format:
<type>(<scope>): <subject>

RULES:
- type MUST be one of: {types_str}{type_hint}
- scope SHOULD be one of: {scopes_str}{scope_hint}
- subject: imperative, present tense, no caps, no period
- Be specific about WHAT changed (e.g., "add parse_large_diff function" not just "update code")

EXAMPLES based on similar changes:
- feat(api): add user authentication endpoint
- fix(db): correct connection pooling issue
- refactor(core): simplify error handling logic

Generate ONLY the commit message (one line):"""
    else:
        # Para diffs pequenos, prompt mais simples
        prompt = f"""Generate a commit message:

Changes:
{diff}

Format: <type>(<scope>): <subject>
Types: {types_str}{type_hint}
Scopes: {scopes_str}{scope_hint}

Message:"""
    
    if retry_count > 0:
        prompt += f"\n\nPrevious suggestion was incomplete. Generate a COMPLETE message."
    
    return prompt


def format_time(seconds: float) -> str:
    """Formata tempo de forma legível"""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    return f"{seconds:.2f}s"


def display_stats(stats: dict, current_provider: str, response_time: float, total_time: float, diff_size: int):
    """Exibe estatísticas de forma profissional"""
    print(f"\n{Colors.INFO}── Performance ──────────────────────────────{Colors.RESET}")
    print(f"{Colors.GRAY}Provider: {Colors.HIGHLIGHT}{current_provider}{Colors.RESET}")
    print(f"{Colors.GRAY}Diff size: {Colors.HIGHLIGHT}{diff_size} lines{Colors.RESET}")
    print(f"{Colors.GRAY}Response: {Colors.HIGHLIGHT}{format_time(response_time)}{Colors.RESET}")
    print(f"{Colors.GRAY}Total:    {Colors.HIGHLIGHT}{format_time(total_time)}{Colors.RESET}")
    
    if stats:
        successful = [f"{p}({d['success']})" for p, d in stats.items() if d['success'] > 0 and p != current_provider]
        if successful:
            print(f"{Colors.GRAY}History: {', '.join(successful)}{Colors.RESET}")
    print(f"{Colors.INFO}────────────────────────────────────────────{Colors.RESET}")


def validate_commit_message(msg: str, pattern: str) -> Tuple[bool, str]:
    """Valida se a mensagem segue o padrão do commit_pattern.md"""
    if not msg:
        return False, "Empty message"
    
    msg = msg.strip()
    if '\n' in msg:
        msg = msg.split('\n')[0]
    
    types = re.findall(r'`(\w+)`:', pattern)
    types_pattern = '|'.join(types) if types else 'feat|fix|docs|style|refactor|perf|test|chore'
    
    # Tenta matching com formato completo: tipo(escopo): assunto
    pattern_regex = rf'^({types_pattern})\(([a-zA-Z0-9_-]+)\): (.+)$'
    match = re.match(pattern_regex, msg)
    
    if not match:
        # Tenta formato simplificado: tipo: assunto
        simple_match = re.match(rf'^({types_pattern}):?\s*(.+)$', msg)
        if simple_match:
            return True, "OK (missing scope, but acceptable)"
        return False, f"Format must be: type(scope): subject"
    
    msg_type, scope, subject = match.groups()
    
    if subject[0].isupper():
        return False, "Subject must not start with capital letter"
    
    if subject.endswith('.'):
        return False, "Subject must not end with period"
    
    if re.search(r'\b(added|changed|fixed|removed|updated)\b', subject.lower()):
        return False, "Use imperative: 'add' not 'added', 'change' not 'changed'"
    
    return True, "OK"


def clean_suggestion(suggestion: Optional[str]) -> Optional[str]:
    """Limpa e valida a sugestão da IA"""
    if not suggestion:
        return None
    
    # Remove aspas e espaços extras
    suggestion = re.sub(r'^["\'`]|["\'`]$', '', suggestion.strip())
    
    # Pega apenas a primeira linha
    lines = suggestion.splitlines()
    if not lines:
        return None
    
    suggestion = lines[0][:MAX_COMMIT_LENGTH]
    
    # Se a mensagem estiver incompleta, tenta completar com a próxima linha
    if suggestion.endswith('(') or suggestion.endswith(':') or len(suggestion) < 15:
        for line in lines[1:3]:
            if ':' in line and len(line) > 20:
                suggestion = line.strip()[:MAX_COMMIT_LENGTH]
                break
    
    return suggestion


# ==========================================
# ORQUESTRADOR PRINCIPAL
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="AI-powered Git commit message generator")
    parser.add_argument("--provider", choices=["groq", "deepseek", "auto"], default="auto", 
                       help="Force specific provider (default: auto)")
    parser.add_argument("--model", type=str, help="Override default model")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--pattern", type=str, default="commit_pattern.md", help="Pattern file to use")
    parser.add_argument("--no-color", action="store_true", dest="no_color", help="Disable colors")
    parser.add_argument("--benchmark", action="store_true", help="Benchmark all providers")
    parser.add_argument("--strict", action="store_true", help="Validate message against pattern")
    parser.add_argument("--force", action="store_true", help="Skip large diff confirmation")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.WARNING
    logging.basicConfig(format="%(levelname)s: %(message)s", level=log_level)

    if args.no_color:
        for attr in dir(Colors):
            if not attr.startswith('__'):
                setattr(Colors, attr, '')

    user_start_time = time.time()

    # Cria o arquivo de padrão se não existir
    create_commit_pattern_file()
    ensure_gitignore()

    # Pega diff e tamanho
    diff, diff_size = get_git_diff(force=args.force)
    if not diff:
        sys.exit(1)

    # Gera resumo para obter tipo e escopo sugeridos
    summary = generate_diff_summary(diff)
    suggested_type = summary['suggested_type']
    suggested_scope = summary['suggested_scope']

    # Carrega o padrão
    pattern_path = os.path.join(os.getcwd(), args.pattern)
    try:
        with open(pattern_path, "r", encoding="utf-8") as f:
            pattern = f.read().strip()
            logging.debug(f"Pattern loaded from: {pattern_path}")
    except FileNotFoundError:
        logging.debug(f"File {args.pattern} not found. Using default rules.")
        pattern = """# Commit Rules
1. Format: <type>(<scope>): <subject>
2. Types: feat, fix, docs, style, refactor, perf, test, chore
3. Scopes: api, ui, db, auth, config, core
4. Subject: imperative, no caps, no period"""

    # Inicializa cliente de IA
    ai_client = AIClient()
    
    if not ai_client.providers:
        print(f"{Colors.ERROR}Error: No API keys found{Colors.RESET}")
        print(f"\n{Colors.WARNING}Configure at least one:{Colors.RESET}")
        print(f"  export DEEPSEEK_API_KEY='your_key'  # Recommended")
        print(f"  export GROQ_API_KEY='your_key'")
        sys.exit(1)

    # Modo benchmark
    if args.benchmark:
        print(f"{Colors.INFO}Benchmark Mode{Colors.RESET}")
        test_prompt = build_optimized_prompt(pattern, diff, diff_size, suggested_type, suggested_scope)
        
        for provider in ai_client.providers:
            print(f"\n{Colors.WARNING}Testing {provider['name']}...{Colors.RESET}")
            start = time.time()
            result = provider['client'].generate_commit(test_prompt, diff_size)
            elapsed = time.time() - start
            
            if result:
                cleaned = clean_suggestion(result)
                print(f"{Colors.SUCCESS}  Success in {format_time(elapsed)}{Colors.RESET}")
                print(f"  Message: {cleaned}")
            else:
                print(f"{Colors.ERROR}  Failed after {format_time(elapsed)}{Colors.RESET}")
        
        sys.exit(0)

    retry_count = 0

    while True:
        # Constrói prompt adaptativo com sugestões do resumo
        current_prompt = build_optimized_prompt(pattern, diff, diff_size, suggested_type, suggested_scope, retry_count)
        
        if args.debug:
            print(f"{Colors.GRAY}Prompt: {current_prompt[:100]}...{Colors.RESET}")
        
        # Gera sugestão com escolha inteligente de provider
        suggestion, provider_used, response_time = ai_client.generate(
            current_prompt, 
            diff_size,
            args.provider if args.provider != "auto" else None
        )
        
        total_time = time.time() - user_start_time

        if not suggestion:
            print(f"{Colors.ERROR}Failed to generate commit suggestion{Colors.RESET}")
            if args.provider != "auto":
                print(f"{Colors.WARNING}Falling back to auto mode...{Colors.RESET}")
                args.provider = "auto"
                continue
            sys.exit(1)

        # Limpa e valida a sugestão
        suggestion = clean_suggestion(suggestion)
        if not suggestion:
            print(f"{Colors.WARNING}Empty suggestion received, retrying...{Colors.RESET}")
            retry_count += 1
            continue
        
        is_valid, validation_msg = validate_commit_message(suggestion, pattern)

        # Mostra estatísticas
        display_stats(ai_client.stats, provider_used, response_time, total_time, diff_size)
        
        # Mostra sugestão
        print(f"\n{Colors.SUCCESS}Suggested message:{Colors.RESET}")
        print(f"{Colors.HIGHLIGHT}{suggestion}{Colors.RESET}")
        
        if args.strict and not is_valid:
            print(f"{Colors.WARNING}Warning: {validation_msg}{Colors.RESET}")
        
        # Menu interativo
        print(f"\n{Colors.INFO}Options: [y] confirm | [r] retry | [e] edit | [n] cancel{Colors.RESET}")
        
        try:
            confirm = input(f"{Colors.INFO}→{Colors.RESET} ").strip().lower()
            
            if confirm == 'y':
                commit_start = time.time()
                subprocess.run(["git", "commit", "-m", suggestion], check=True)
                commit_time = time.time() - commit_start
                
                print(f"{Colors.SUCCESS}Commit successful ({format_time(commit_time)}){Colors.RESET}")
                break
                
            elif confirm == 'r':
                retry_count += 1
                print(f"{Colors.INFO}Retrying...{Colors.RESET}")
                continue
                
            elif confirm == 'e':
                manual = input(f"{Colors.INFO}Enter message: {Colors.RESET}").strip()
                if manual:
                    if args.strict:
                        is_valid, msg = validate_commit_message(manual, pattern)
                        if not is_valid:
                            print(f"{Colors.WARNING}Warning: {msg}{Colors.RESET}")
                            proceed = input(f"{Colors.INFO}Commit anyway? (y/N): {Colors.RESET}").lower()
                            if proceed != 'y':
                                continue
                    
                    subprocess.run(["git", "commit", "-m", manual], check=True)
                    print(f"{Colors.SUCCESS}Commit successful{Colors.RESET}")
                break
                
            else:
                print(f"{Colors.WARNING}Cancelled{Colors.RESET}")
                break
                
        except subprocess.CalledProcessError:
            logging.error("Git commit failed")
            break
        except KeyboardInterrupt:
            print(f"\n{Colors.WARNING}Cancelled{Colors.RESET}")
            sys.exit(0)
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            break

if __name__ == "__main__":
    main()