
def confirm(text: str) -> bool:
    prompt = f"{text} [y/N]"
    while True:
        try:
            value = input(prompt).lower().strip()
        except (KeyboardInterrupt, EOFError):
            raise # TODO
        if value == 'y' or value == 'yes':
            rv = True
        elif value == 'n' or value == 'no':
            rv = False
        else:
            print(f"Invalid input")
            continue
        return rv
    return False
