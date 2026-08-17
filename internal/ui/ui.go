package ui

import (
	"bufio"
	"fmt"
	"os"
	"strings"
)

// ANSI color codes. The palette is intentionally sober (standard terminal
// colors) so that visual hierarchy comes from color + text indicator, not
// brightness or decorative characters.
const (
	reset  = "\033[0m"
	bold   = "\033[1m"
	green  = "\033[32m" // success
	yellow = "\033[33m" // warning / secondary action
	gray   = "\033[90m" // muted / informational
	red    = "\033[31m" // errors
)

var debug bool

// SetDebug toggles detailed debug logging on stdout.
func SetDebug(v bool) { debug = v }

// Debug prints a muted [DEBUG] line when debug mode is enabled.
func Debug(msg string) {
	if debug {
		fmt.Printf("%s[DEBUG] %s%s\n", gray, msg, reset)
	}
}

// Success prints a "[OK]" line with an aligned label and a detail message.
func Success(label, detail string) {
	fmt.Printf("%s[OK]%s %-35s %s\n", green, reset, label, detail)
}

// Info prints a muted, indented informational line.
func Info(msg string) {
	fmt.Printf("  %s%s%s\n", gray, msg, reset)
}

// Warn prints a yellow "[AVISO]" warning line.
func Warn(msg string) {
	fmt.Printf("%s[AVISO] %s%s\n", yellow, msg, reset)
}

// Error prints a red "[ERRO]" line to stderr.
func Error(msg string) {
	fmt.Fprintf(os.Stderr, "%s[ERRO] %s%s\n", red, msg, reset)
}

// Fatal prints a red "[FATAL]" line to stderr and exits with status 1.
func Fatal(msg string) {
	fmt.Fprintf(os.Stderr, "%s[FATAL] %s%s\n", red, msg, reset)
	os.Exit(1)
}

// Suggestion prints the generated commit message suggestion.
func Suggestion(msg string) {
	fmt.Printf("\n%sSugestão de commit:%s %s%s%s\n", bold, reset, green, msg, reset)
}

// Confirm prompts for the commit decision (Y/R/N) and returns the normalized
// answer.
func Confirm() string {
	fmt.Printf("\n%s[Y]%s Confirmar   %s[R]%s Recriar   %s[N]%s Cancelar\n%s> %s",
		bold+green, reset,
		bold+yellow, reset,
		bold+gray, reset,
		bold, reset,
	)
	reader := bufio.NewReader(os.Stdin)
	input, _ := reader.ReadString('\n')
	return strings.ToLower(strings.TrimSpace(input))
}

// ProgressStart prints the "generating" indicator and flushes stdout so the
// user sees it before the (potentially slow) HTTP request begins.
func ProgressStart() {
	fmt.Print(gray + "Gerando sugestão... " + reset)
	_ = os.Stdout.Sync()
}

// ProgressClear removes the "generating" indicator from the terminal line.
func ProgressClear() {
	fmt.Print("\r" + strings.Repeat(" ", 60) + "\r")
}
