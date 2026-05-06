import os


debug = lambda *args, **kwargs: ()
def _debug(msg, *args):
    from pprint import pprint
    print(f'[CUI_DEBUG] {msg}')
    if args:
        if len(args) == 1:
            args = args[0]
        pprint(args)

if os.environ.get('HCUI_DEBUG', '0') == '1':
    debug = _debug
