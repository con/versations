# Versations

Versations is a lightweight CLI based on [nio](https://matrix-nio.readthedocs.io/en/latest/)

It is designed to be run by a cronjob, syncs with Matrix rooms and
records messages as simple text in the following structure:

    room-name /
       YYYY-MM-DD

It can also send messages (a string or from a file) at the time of the
run.

See `versations --help` for usage.

## Installation

`versations` depends on matrix-nio, which requires the `libolm` C
library, which can be installed (on debian and fedora) as package
`libolm-dev`. See [nio
docs](https://matrix-nio.readthedocs.io/en/latest/) for more
information.

With libolm installed, it can be installed via `git clone` and `pip
install .`
