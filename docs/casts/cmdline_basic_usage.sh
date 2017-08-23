
say "Welcome to this screencast on datalad. It briefly describes the basic concept of datalad's command line API"
type 'cowsay "Using $(datalad --version 2>&1 | head -n1)"'
execute

say "All of data-lad's functionality is available through a single command"
type 'clear'; execute
say "It's name is: datalad"
type "datalad"

say "Running the datalad command without any arguments, give a summary of basic option, and a list of available sub commands."
execute

say "More comprehensive information is available via the dash dash help option"
key Return Return; sleep 1
type "datalad --help"
execute
say "This either prints information in the terminal, or it opens a manpage, when one is available."
key --delay 50 $(printf 'Down %.0s' {1..100}) sleep 1 key q

say "Getting information on any of the available sub commands works in the same way. Type: datalad."
type 'datalad'
say "The name of the sub command, for example, create."
type ' create'
say "followed by dash dash help"
type " --help"
execute; sleep 1
key --delay 25 $(printf 'Down %.0s' {1..100}) sleep 1 key q

sleep 2
say "For more information, visit datalad.org."

