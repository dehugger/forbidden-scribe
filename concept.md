# forbidden scribe

rough-to-middle fiction draft writer using ai refinement of raw user input

to many views, user input of raw text below, vertical scrolling list of "passages" above, where each passage is a text-paring between the user input and response it generated
this is stored in a json formatted document file.

the tui allows swapping between text editing in the user input box and scrolling through the generated passages (which, combined, form the story document).
at each passage the user can either press LEFT to see menu options for 1/2 the core functions. if they hit right, they get the other 1/2. there are also hotkeys for each option
options include:
- reroll (re-generate) passage via same settings
- reroll passage with unbounded token return limit
- reroll passage with additional instructions
- send passage to "fix" agent that removes invalid bits like thinking text or prepend/append text taht shouldnt have been included
- send a passage to a write agent that condenses it
- send a passage to a write agent that expands it
- send a passage to a write agent with additional instructions
if they hit ENTER directly on the passage itself they go into manual edit mode on it, and it gets more screen focus, and displays information about the passage arround it (from the json document)

each passage is slightly seperated vertically, and they have small colored indicators or outlines or something like that to seperate them visually

theres keybindings, a default forbidden-scribe prompt, and an option to use alternate system prompts. there is also config settings for the model + parameters.
the agent is also to respond in a specific json schema

it is planned to add information to the passage json about what agent generated it, and a full audit log history of all changes

