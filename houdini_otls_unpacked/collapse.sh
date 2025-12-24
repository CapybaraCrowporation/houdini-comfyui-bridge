#!/usr/bin/env bash
set -e -o pipefail

pushd $(realpath $(dirname $0))

for name in *.hda; do
    echo Collapsing \"$name\"
    hotl -l "$name" "../houdini/otls/$name"
done

popd
