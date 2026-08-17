package commit

import (
	"os"
	"os/exec"
)

// Execute runs "git commit -m <msg>" against the current repository,
// streaming git's stdout/stderr to the terminal.
func Execute(msg string) error {
	cmd := exec.Command("git", "commit", "-m", msg)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}
