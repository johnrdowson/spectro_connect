# spectro_connect

A CLI tool to connect to devices via a SpectroServer instance (DX Spectrum)

## Installation

`pip install spectro_connect`

## Usage

```bash
$ spectro_connect --help
usage: spectro_connect [-h] [-s SPECTRO_IP] [-p PORT] [-t] [-v] host

SpectroServer Connect Tool

positional arguments:
  host                  IP address or name of remote device to connect to

optional arguments:
  -h, --help            show this help message and exit
  -s SPECTRO_IP, --spectro_ip SPECTRO_IP
                        IP address of SpectroServer
  -p PORT, --port PORT  Port to connect to on remote device
  -t, --telnet          Connect using Telnet
  -v, --verbose         Verbose output
```

## Environment Variables

To specify the SpectroServer IP (rather than using the `-s` flag each time):

- `SPECTROSERVER_HOST`

To enable Spectrum OneClick integration for device name lookups (recommended):

- `SPECTRUM_URL` - URL of Spectrum OneClick
- `SPECTRUM_USERNAME` - Username to access Spectrum OneClick
- `SPECTRUM_PASSWORD` - Password to access Spectrum OneClick

## Example Usage

This tool provides an SSH or Telnet session to a device managed in Spectrum.
The connection is relayed through SpectroServer, using the same mechanism as
the Spectrum Client Console.

In Windows, a PuTTY connection will be launched. In Linux, it will use the
built-in SSH client.

If just an IP address is provided, it will attempt to estabish an SSH
connection:

```bash
spectro_connect 172.31.100.20
```

If there environment variable `SPECTROSERVER_HOST` is not defined, the IP
address of the SpectroServer must be provided after the `-s` flag:

```bash
spectro_connect -s 10.30.40.100 172.31.100.20
```

You can force a Telnet connection by including the `--telnet` flag:

```bash
spectro_connect 172.31.100.20 --telnet
```

If a hostname is provided (i.e. anything other than an IPv4 address), a lookup
of the name will be done via the Spectrum API. If a single match is found, the
script will connect using the appropriate protocol, based on the NCM family of
that particular device:

```bash
spectro_connect CORE_RTR01
```