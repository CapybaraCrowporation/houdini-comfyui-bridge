import sys
import argparse
import re
import json
from pathlib import Path


def do_prune(location: Path, keep_rules: dict[str, str]|None, *, dry_run: bool = False):
    assets: dict[str, list[tuple[tuple[int, ...], Path]]] = {}
    for path in location.iterdir():
        if not path.suffix in ('.hda', '.otl'):
            continue
        m = re.match(r'^(.*\D)\.(\d+(?:\.\d+)*)\.(?:hda|otl)$', path.name)
        if not m:  # ignore assets with no versions
            continue
        ver = tuple(int(x) for x in m.group(2).split('.'))
        name = m.group(1)
        assets.setdefault(name, []).append((ver, path))

    for ass_name, ass_list in assets.items():
        del_list = []
        rule = (keep_rules or {}).get(ass_name, 'latest')
        print('-', ass_name, 'rule:', repr(rule))
        # rudimantary check for now
        if rule == "*":  # keep all
            continue
        elif rule == "":  # keep none
            del_list = [x[1] for x in ass_list]
        elif rule == "latest":  # default behaviour - keep latest version only
            ass_list = sorted(ass_list, key=lambda x: x[0])
            del_list = [x[1] for x in ass_list[:-1]]
        else:
            # rules like >=1.2,<3
            rex = re.compile(r'^(.*?)(\d(:?\.\d)*)$')
            vmin, vmin_include = (), False
            vmax, vmax_include = (), False

            def _adjust_min(ver, include):
                nonlocal vmin, vmin_include
                if not vmin or ver > vmin:
                    vmin = ver
                    vmin_include = include
                elif ver == vmin and vmin_include:
                    vmin_include = include
            
            def _adjust_max(ver, include):
                nonlocal vmax, vmax_include
                if not vmax or ver < vmax:
                    vmax = ver
                    vmax_include = include
                elif ver == vmax and vmax_include:
                    vmax_include = include

            for rule_part in (x.strip() for x in rule.split(',')):
                m = rex.match(rule_part)
                if not m:
                    raise ValueError(f'incorrect version specification: "{rule_part}"')
                comp = m.group(1)
                ver = tuple(int(x) for x in m.group(2).split('.'))
                if comp == '':  # exact version
                    _adjust_min(ver, True)
                    _adjust_max(ver, True)
                elif comp in ('>', '>='):
                    _adjust_min(ver, comp == '>=')
                elif comp in ('<', '<='):
                    _adjust_max(ver, comp == '<=')
                else:
                    raise NotImplementedError(f'comparison type "{comp}" is not implemented for versions')
            
            # now filter assets
            for ver, path in sorted(ass_list, key=lambda x: x[0]):
                if vmin and (ver <= vmin and not vmin_include or ver < vmin and vmin_include):
                    del_list.append(path)
                if vmax and (ver >= vmax and not vmax_include or ver > vmax and vmax_include):
                    del_list.append(path)
        for path in del_list:
            if dry_run:
                print(f'would delete {path}')
            else:
                print(f'deleting {path}')
                path.unlink()


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('src')
    parser.add_argument('dst', nargs='?')
    parser.add_argument('--rules-file', nargs='?')
    parser.add_argument('--dry-run', action='store_true')

    options = parser.parse_args(argv)

    src = options.src
    if dst := options.dst:
        raise NotImplementedError('tbd')

    rules = {}
    if options.rules_file:
        with open(options.rules_file) as f:
            rules = json.load(f)

    do_prune(Path(src), rules, dry_run=options.dry_run)


if __name__ == '__main__':
    main(sys.argv[1:])
