import hou


def show_error(text: str, details: str|None = None, title: str|None = None):
    if hou.isUIAvailable():
        try:
            hou.ui.displayMessage(
                text,
                severity=hou.severityType.Error,
                title=title,
                details=details,
            )
        except hou.OperationInterrupted:
            # displayMessage reraises OperationInterrupted for some reason
            pass
    else:
        print(text)
