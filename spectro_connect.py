#!/usr/bin/env python

"""
Author: John Dowson
Purpose: Connect to a remote device via SpectroServer.
"""

import socket
import sys
import logging
import threading
import argparse
import ipaddress
import os
import requests
import platform
from lxml import etree
from typing import List, Dict
from subprocess import Popen


SPECTRUM_URL = os.getenv("SPECTRUM_URL")
SPECTRUM_USERNAME = os.getenv("SPECTRUM_USERNAME")
SPECTRUM_PASSWORD = os.getenv("SPECTRUM_PASSWORD")
SPECTROSERVER_HOST = os.getenv("SPECTROSERVER_HOST")
SPECTROSERVER_PORT = os.getenv("SPECTROSERVER_PORT", 31415)
DEFAULT_PORTS = {"ssh": 22, "telnet": 23}
TELNET_PLATFORMS = ["8519702"]


def is_ipv4(string: str) -> bool:
    """Returns True if string is a valid IPv4 address"""
    try:
        ipaddress.ip_address(string)
        return True
    except ValueError:
        return False


def strip_ns(root: etree.Element) -> etree.Element:
    """
    This function removes all namespace information from an XML Element tree
    so that a Caller can then use the `xpath` function without having
    to deal with the complexities of namespaces.
    """

    # first we visit each node in the tree and set the tag name to its
    # localname value; thus removing its namespace prefix

    for elem in root.getiterator():
        elem.tag = etree.QName(elem).localname

    # at this point there are no tags with namespaces, so we run the cleanup
    # process to remove the namespace definitions from within the tree.

    etree.cleanup_namespaces(root)
    return root


def spectrum_device_search_by_name(name: str) -> List[Dict[str, str]]:
    """
    Search for devices which match the given hostname and return the hostnames
    and Spectrum model handles
    """

    # Construct the necesary API components to make an API request to Spectrum

    url = f"{SPECTRUM_URL}/spectrum/restful/models"
    headers = {"Content-Type": "application/xml"}
    auth = (SPECTRUM_USERNAME, SPECTRUM_PASSWORD)

    # XML payload that will instruct Spectrum to search devices and use the
    # filter provided i.e. devices with a model name that contains the given
    # hostname string (case ignored).

    payload = f"""<?xml version="1.0" encoding="UTF-8"?>
    <rs:model-request
    xmlns:rs="http://www.ca.com/spectrum/restful/schema/request"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    throttlesize="60000"
    xsi:schemaLocation="http://www.ca.com/spectrum/restful/schema/request
    ../../../xsd/Request.xsd">
        <rs:target-models>
            <rs:models-search>
                <rs:search-criteria
                xmlns="http://www.ca.com/spectrum/restful/schema/filter">
                    <devices-only-search>
                    </devices-only-search>
                    <filtered-models>
                        <has-substring-ignore-case>
                            <model-name>{name}</model-name>
                        </has-substring-ignore-case>
                    </filtered-models>
                </rs:search-criteria>
            </rs:models-search>
        </rs:target-models>
        <rs:requested-attribute id="0x1006e" />  <!-- Model Name -->
        <rs:requested-attribute id="0x12d7f" />  <!-- IP Address -->
        <rs:requested-attribute id="0x12bef" />  <!-- NCM Device Family -->
    </rs:model-request>
    """

    # Send the POST request to Spectrum OC

    resp = requests.post(url=url, headers=headers, auth=auth, data=payload)

    # Raise exception if HTTP error occurred

    resp.raise_for_status()

    # Parse the XML and strip namespace

    root = etree.fromstring(resp.content)
    root = strip_ns(root)

    # If any devices are found, these will appear in the 'model' element nodes
    # We first check if there are any at all, then loop through the results
    # and append each one to the 'devices' list, which is then returned.

    devices_found = []
    models = root.xpath("model-responses")[0]
    # print(etree.tostring(models, pretty_print=True).decode())

    if len(models) > 0:
        names = models.xpath("model/attribute[@id='0x1006e']/text()")
        ip_addrs = models.xpath("model/attribute[@id='0x12d7f']/text()")
        platforms = models.xpath("model/attribute[@id='0x12bef']/text()")
        handles = models.xpath("model/@mh")
        for index, name in enumerate(names):
            devices_found.append(
                {
                    "mh": handles[index],
                    "name": name,
                    "ip_addr": ip_addrs[index],
                    "pfm": platforms[index],
                }
            )

    return devices_found


def transfer(src: socket.socket, dst: socket.socket, send: bool) -> None:
    """
    Send data received on the source socket to the destination socket.
    """
    src_addr, src_port = src.getsockname()
    dst_addr, dst_port = dst.getsockname()
    while True:
        try:
            buffer = src.recv(0x400)
        except socket.error:
            break
        if len(buffer) == 0:
            logging.debug("[-] No data received! Breaking...")
            break
        try:
            dst.send(buffer)
        except socket.error:
            break
    logging.debug(f"[+] Closing connections! [{src_addr}:{src_port}]")
    try:
        src.shutdown(socket.SHUT_RDWR)
        src.close()
    except socket.error:
        pass
    logging.debug(f"[+] Closing connections! [{dst_addr}:{dst_port}]")
    try:
        dst.shutdown(socket.SHUT_RDWR)
        dst.close()
    except socket.error:
        pass


def create_server_socket(local_port: int = 0) -> socket.socket:
    """
    Creates a new socket object and binds that to the localhost on a free port
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("127.0.0.1", local_port))
    return server_socket


def start_server(
    server_socket: socket.socket,
    spectro_ip: str,
    spectro_port: int,
    device_ip: str,
    device_port: int,
) -> None:
    """
    Main server function that will connect to SpectroServer and initate the
    relayed connection.

    A TX and RX transfer threads are then created, creating a reverse TCP
    proxy which will listen on the given socket.
    """

    # Start listening on server socket
    logging.debug("[+] Starting server")
    server_socket.listen()

    # Wait for incoming connection on server socket
    logging.debug("[+] Waiting for incoming connection")
    client_socket, client_addr = server_socket.accept()
    logging.debug(
        f"[+] Connection detected from [{client_addr[0]}:{client_addr[1]}]"
    )

    # Connect to SpectroServer and issue relay command
    logging.info(
        f"[+] Connecting to host [{device_ip}:{device_port}] "
        f"via SpectroServer [{spectro_ip}:{spectro_port}]"
    )
    relay_cmd = f"relay {device_ip} {str(device_port)}\r\n"
    remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    remote_socket.connect((spectro_ip, spectro_port))
    remote_socket.send(relay_cmd.encode("ascii"))
    logging.debug("[+] Tunnel connected! Transferring data...")

    # Create the send and receive threads for transfering data between sockets
    snd_thread = threading.Thread(
        target=transfer, args=(remote_socket, client_socket, False)
    )
    rcv_thread = threading.Thread(
        target=transfer, args=(client_socket, remote_socket, True)
    )

    # Start the transfer threads
    snd_thread.start()
    rcv_thread.start()

    # Wait for threads to terminate
    snd_thread.join()
    rcv_thread.join()

    # Close down the sockets
    logging.debug("[+] Releasing resources...")
    try:
        remote_socket.shutdown(socket.SHUT_RDWR)
        remote_socket.close()
    except socket.error:
        pass
    try:
        client_socket.shutdown(socket.SHUT_RDWR)
        client_socket.close()
    except socket.error:
        pass
    logging.debug("[+] Closing the server...")
    try:
        server_socket.shutdown(socket.SHUT_RDWR)
        server_socket.close()
    except socket.error:
        pass
    logging.debug("[+] Server shutdown!")


def console_dispath(platform: str, **kwargs) -> None:
    """Select console method based on host OS"""
    console_functions = {
        "windows": start_putty_session,
        "linux": start_shell_session,
    }
    func = console_functions.get(platform.lower(), start_shell_session)
    return func(**kwargs)


def start_putty_session(
    server_ip: str,
    server_port: int,
    device_ip: str,
    protocol: str = "ssh",
    **kwargs,
) -> None:
    """Start PuTTY Session when using Windows"""

    putty_cmd = (
        f"powershell putty.exe -{protocol} {server_ip} "
        f"-P {server_port} "
        f"-loghost {device_ip}"
    )
    logging.debug(f"[+] Starting PuTTY with [{putty_cmd}]")
    Popen(putty_cmd)


def start_shell_session(
    server_ip: str,
    server_port: int,
    device_ip: str,
    protocol: str = "ssh",
    **kwargs,
) -> None:
    """Start Shell Session when using Linux (inc. WSL)"""

    if protocol == "telnet":
        bash_cmd = f"telnet {server_ip} {server_port}"
    else:
        bash_cmd = (
            f"ssh -o HostKeyAlias={device_ip} "
            f"-o KexAlgorithms=+diffie-hellman-group1-sha1,"
            f"diffie-hellman-group-exchange-sha1 "
            f"-o Ciphers=+aes256-cbc "
            f"{input('Username: ')}@{server_ip} -p {server_port}"
        )

    logging.debug(f"[+] Starting session with [{bash_cmd}]")
    Popen(bash_cmd, shell=True)


def main() -> None:
    """
    Execution starts here
    """

    # Collect and process arguments

    args = _process_args()

    # Set logging level

    logging.basicConfig(
        level=args.loglevel,
        format="[%(levelname)s] (%(threadName)-10s) %(message)s",
    )

    # If host is an IPv4 address, use this as the device IP. Otherwise,
    # perform Spectrum lookup

    if is_ipv4(args.host):
        device_ip = args.host
        protocol = args.protocol
    else:
        devices = spectrum_device_search_by_name(args.host)

        if len(devices) == 1:
            logging.info(f"[+] Found device [{devices[0]['name']}]")
            device_ip = devices[0]["ip_addr"]
            protocol = (
                "telnet"
                if devices[0]["pfm"] in TELNET_PLATFORMS
                else args.protocol
            )
        elif len(devices) > 1:
            print("Error: Mulitple device matches found:")
            for device in sorted(devices, key=lambda i: i["name"]):
                print(f"{device.get('name')} ({device.get('ip_addr')})")
            sys.exit(1)
        else:
            print(f'Error: No device with name "{args.host}" found')
            sys.exit(1)

    # Use port argument if provided, otherwise use protocol default
    device_port = args.port or DEFAULT_PORTS.get(protocol)

    # Check for SpectroServer IP
    if args.spectro_ip:
        spectro_ip = args.spectro_ip
    # elif SPECTROSERVER_HOST:
    #     spectro_ip = SPECTROSERVER_HOST
    else:
        print("No SpectroServer IP address provided.")
        print(
            'Either add as argument (e.g. "-s 10.20.30.4") '
            "or configure as SPECTROSERVER_HOST enviroment variable."
        )
        sys.exit(1)

    # Create server socket
    server_socket = create_server_socket(args.local_port)
    server_ip, server_port = server_socket.getsockname()
    logging.debug(f"[+] Created server socket on [{server_ip}:{server_port}]")

    # Start server thread
    svr_thread = threading.Thread(
        target=start_server,
        args=(
            server_socket,
            spectro_ip,
            SPECTROSERVER_PORT,
            device_ip,
            device_port,
        ),
    )
    svr_thread.daemon = True
    svr_thread.start()

    if args.proxy:
        # Just output the local socket information
        logging.info(
            f"[+] Proxy socket details: {server_ip}:{server_port}. "
            f"Awaiting connection..."
        )
    else:
        # Launch console session based on local OS
        console_dispath(
            platform=platform.system(),
            protocol=protocol,
            server_ip=server_ip,
            server_port=server_port,
            device_ip=device_ip,
        )

    # Wait for server thread to terminate
    svr_thread.join()


def _check_ip(ip_addr: str) -> str:
    """Validate IP address"""
    if not is_ipv4(ip_addr):
        msg = f"{ip_addr} is not a valid IPv4 address"
        raise argparse.ArgumentTypeError(msg)
    return ip_addr


def _check_host(hostname: str) -> str:
    """Validate hostname is an IP address if not using Spectrum Lookup"""
    valid_spectrum = all([SPECTRUM_URL, SPECTRUM_USERNAME, SPECTRUM_PASSWORD])
    if not valid_spectrum and not is_ipv4(hostname):
        msg = (
            f"{hostname} is not a valid IPv4 address. "
            f"Spectrum info is not provided so cannot perform lookup."
        )
        raise argparse.ArgumentTypeError(msg)
    return hostname


def _check_port(port: str) -> int:
    """Validate TCP/IP port"""
    iport = int(port)
    if iport not in range(1, 65535):
        msg = f"{port} is not a valid port"
        raise argparse.ArgumentTypeError(msg)
    return iport


def _process_args() -> argparse.Namespace:
    """
    Process command line arguments.
    """

    # Parse CLI arguments
    parser = argparse.ArgumentParser(description="SpectroServer Connect Tool")
    parser.add_argument(
        "host",
        help="IP address or name of remote device to connect to",
        type=_check_host,
    )
    parser.add_argument(
        "-s",
        "--spectro_ip",
        help="IP address of SpectroServer",
        default=SPECTROSERVER_HOST,
        type=_check_ip,
    )
    parser.add_argument(
        "-p",
        "--port",
        help="Port to connect to on remote device",
        type=_check_port,
    )
    parser.add_argument(
        "-l",
        "--local_port",
        help="Local port to use for local proxy socket",
        type=_check_port,
        default=0,
    )
    parser.add_argument(
        "-x",
        "--proxy",
        help="Just provide a local proxy socket",
        action="store_true",
    )
    parser.add_argument(
        "-t",
        "--telnet",
        help="Connect using Telnet",
        action="store_const",
        dest="protocol",
        const="telnet",
        default="ssh",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="Verbose output",
        action="store_const",
        dest="loglevel",
        const=logging.DEBUG,
        default=logging.INFO,
    )

    return parser.parse_args()


if __name__ == "__main__":
    exit(main())
