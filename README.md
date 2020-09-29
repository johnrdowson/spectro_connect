# Spectrum Tools

A collection of tools which utilise an existing CA Spectrum environment.

## Installation

1. Clone the repository to your machine:

    ```bash
    git clone https://github.com/johnrdowson/spectrum_tools.git
    ```

2. (Optional) Create and activate a new Python virtual environment:

    - Linux/macOS:

        ```bash
        python -m venv venv
        source venv/bin/activate
        ```

    - Windows (Git Bash):

        ```bash
        py -3 -m venv venv
        source venv/Scripts/activate
        ```

3. Install dependancies:

    ```bash
    pip install -r requirements
    ```

4. (Optional) Add environment variable `SPECTROSERVER_HOST` for SpectroServer's
   IP address:

    ```bash
    echo export "SPECTROSERVER_HOST=10.30.40.100" >> ~/.bash_profile
    ```

5. (Optional) For Spectrum integration (i.e. name lookups), add the following
   environment variables:

     - `SPECTRUM_URL` - Spectrum OneClick URL
     - `SPECTRUM_USERNAME` - Username to access Spectrum OneClick
     - `SPECTRUM_PASSWORD` - Password to access Spectrum OneClick

    Example:

    ```bash
    echo export "SPECTRUM_URL=http://spectrum-oc:8080" >> ~/.bash_profile
    echo export "SPECTRUM_USERNAME=operator" >> ~/.bash_profile
    echo export "SPECTRUM_PASSWORD=P@55w0rd123!" >> ~/.bash_profile
    ```

## Usage

### Spectrum Connect

This tool provides an SSH or Telnet session to a device managed in Spectrum.
The connection is relayed through SpectroServer, using the same mechanism as
the Spectrum Client Console.

In Windows, a PuTTY connection will be launched. In Linux, it will use the
built-in SSH client.

If just an IP address is provided, it will attempt to estabish an SSH
connection:

```bash
python spectro_connect.py 172.31.100.20
```

If there environment variable `SPECTROSERVER_HOST` is not defined, the IP
address of the SpectroServer must be provided after the `-s` flag:

```bash
python spectro_connect.py -s 10.30.40.100 172.31.100.20
```

You can force a Telnet connection by including the `--telnet` flag:

```bash
python spectro_connect.py 172.31.100.20 --telnet
```

If a hostname is provided (i.e. anything other than an IPv4 address), a lookup
of the name will be done via the Spectrum API. If a single match is found, the
script will connect using the appropriate protocol, based on the NCM family of
that particular device:

```bash
python spectro_connect.py CORE_RTR01
```