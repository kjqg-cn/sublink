#!/bin/sh
set -eu

mkdir -p /app/app/db

if [ "$(id -u)" = "0" ]; then
    chown -R sublink:sublink /app/app/db
    exec gosu sublink "$@"
fi

exec "$@"
