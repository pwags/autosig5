#!/usr/bin/env python

"""
autosig.py

Generates the System Implementation Guide.

Copyright (c) 2014  Nexenta Systems
William Kettler <william.kettler@nexenta.com>
Pete Hartman <pete.hartman@nexenta.com>
"""

import os
import sys
import subprocess
import signal
import getopt
import simplejson
import datetime

# Define globals for convenience and to avoid complex passing
version = "0.2"
collector = None
sig = None
ignore = False


def usage():
    """
    Print usage.

    Inputs:
        None
    Outputs:
        None
    """
    cmd = sys.argv[0]

    print "%s [-h] [-c CONFIG] [-C COLLECTORDIR] [-i]" % cmd
    print ""
    print "Nexenta Auto-SIG"
    print ""
    print "Arguments:"
    print ""
    print "    -h, --help           print usage"
    print "    -c, --config         config file"
    print "    -C, --collector      collector directory"
    print "    -i, --ignore         ignore errors"


class Timeout(Exception):
    pass


class Execute(Exception):
    pass


def alarm_handler(signum, frame):
    raise Timeout


def execute(cmd, timeout=None):
    """
    Execute a command in the default shell. If a timeout is defined the command
    will be killed if the timeout is exceeded.

    Inputs:
        cmd     (str): Command to execute
        timeout (int): Command timeout in seconds
    Outputs:
        retcode  (int): Return code
        output  (list): STDOUT/STDERR
    """
    # Define the timeout signal
    if timeout:
        signal.signal(signal.SIGALRM, alarm_handler)
        signal.alarm(timeout)

    try:
        # Execute the command and wait for the subprocess to terminate
        # STDERR is redirected to STDOUT
        phandle = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)

        # Read the stdout/sterr buffers and retcode
        stdout, stderr = phandle.communicate()
        retcode = phandle.returncode
    except Timeout, t:
        # Kill the running process
        phandle.kill()
        raise Timeout("command timeout of %ds exceeded" % timeout)
    except Exception, err:
        raise Execute(err)
    else:
        # Possible race condition where alarm doesn't disabled in time
        signal.alarm(0)

    # stdout may be None and we need to acct for it
    if stdout and stdout is not None:
        output = stdout.strip()
    else:
        output = None

    return retcode, output


def execute_collector(location, timeout=None):
    """
    Read data from collector as defined in the config file and write it to
    the SIG document.

    Inputs:
        location (str): collector file to read
        timeout  (int): Command timeout in seconds
    Outputs:
        None
    """
    # allow null to ignore this for higher levels of the document tree
    if not location:
        return

    try:
        retcode, output = execute("cat %s/%s" % (collector, location),
                                  timeout=timeout)
    except Exception, err:
        log("ERROR", "could not read file \"%s/%s\"" % (collector, location))
        log("ERROR", str(err))
        if not ignore:
            sys.exit(1)

    # Check the command return code
    if retcode:
        log("ERROR", "collector read failed \"%s/%s\"" % (collector, location))
        log("ERROR", output)
        if not ignore:
            sys.exit(1)

    sig.print_string("[%s/%s]" % (collector, location))
    sig.print_newline()
    sig.print_paragraph(output)


def execute_cmd(cmd, timeout=None):
    """
    Execute a command as defined in the config file and write it to the SIG
    document.

    Inputs:
        cmd     (str): Command to execute
        timeout (int): Command timeout in seconds
    Outputs:
        None
    """
    try:
        retcode, output = execute(cmd, timeout=timeout)
    except Exception, err:
        log("ERROR", "command execution failed \"%s\"" % cmd)
        log("ERROR", str(err))
        if not ignore:
            sys.exit(1)

    # Check the command return code
    if retcode:
        log("ERROR", "command execution failed \"%s\"" % cmd)
        log("ERROR", output)
        if not ignore:
            sys.exit(1)

    sig.print_string("[%s]" % cmd)
    sig.print_newline()
    sig.print_paragraph(output)


def execute_nmc(cmd, timeout=None):
    """
    Execute an NMC command as defined in the config file and write it to the
    SIG document.

    Inputs:
        cmd     (str): NMC command to execute
        timeout (int): Command timeout in seconds
    Outputs:
        None
    """
    nmc = "nmc -c \"%s\"" % cmd
    try:
        retcode, output = execute(nmc, timeout=timeout)
    except Exception, err:
        log("ERROR", "NMC command execution failed \"%s\"" % cmd)
        log("ERROR", str(err))
        if not ignore:
            sys.exit(1)

    # Check the command return code
    if retcode:
        log("ERROR", "NMC command execution failed \"%s\"" % cmd)
        log("ERROR", output)
        if not ignore:
            sys.exit(1)

    sig.print_string("[%s]" % nmc)
    sig.print_newline()
    sig.print_paragraph(output)


def ssh(cmd, host, timeout=None):
    """
    Execute a command on a remote host as defined in the config file and write
    it to the SIG document.

    Inputs:
        cmd     (str): Command to execute
        host    (str): Remote host
        timeout (int): Command timeout in seconds
    Output:
        None
    """
    ssh_nmc = "ssh %s \"%s\"" % (host, cmd)
    try:
        retcode, output = execute(ssh_nmc, timeout)
    except Exception, err:
        log("ERROR", "SSH command execution failed \"%s\"" % ssh)
        log("ERROR", str(err))
        if not ignore:
            sys.exit(1)

    # Check the command return code
    if retcode:
        log("ERROR", "SSH command execution failed \"%s\"" % ssh)
        log("ERROR", output)
        if not ignore:
            sys.exit(1)

    sig.print_string("[%s]" % cmd)
    sig.print_newline()
    sig.print_paragraph(output)


def ssh_nmc(cmd, host, timeout=None):
    """
    Execute an NMC command on a remote host as defined in the config file
    and write it to the SIG document.

    Inputs:
        cmd     (str): NMC command to execute
        host    (str): Remote host
        timeout (int): Command timeout in seconds
    Outputs:
        None
    """
    nmc = "nmc -c \"%s\"" % cmd
    ssh_nmc = "ssh %s \"%s\"" % (host, nmc)
    try:
        retcode, output = execute(ssh_nmc, timeout)
    except Exception, err:
        log("ERROR", "SSH NMC command execution failed \"%s\"" % ssh_nmc)
        log("ERROR", str(err))
        if not ignore:
            sys.exit(1)

    # Check the command return code
    if retcode:
        log("ERROR", "SSH NMC command execution failed \"%s\"" % ssh_nmc)
        log("ERROR", output)
        if not ignore:
            sys.exit(1)

    sig.print_string("[%s]" % nmc)
    sig.print_newline()
    sig.print_paragraph(output)


def log(severity, message):
    """
    Log a message to stdout.

    Inputs:
        severity (str): Severity string
        message  (str): Log message
    Outputs:
        None
    """
    print " %s [%s] %s" % (str(datetime.datetime.now()), severity, message)


class Document:

    def __init__(self, f, stdout=False):
        self.stdout = stdout
        self.fh = open(f, 'w')

    def _write(self, s):
        """
        Wrapper function for the write method.

        Inputs:
            s (str): String
        Output:
            None
        """
        self.fh.write(s)
        self.fh.flush()

        # Write to stdout if defined
        if self.stdout:
            sys.stdout.write(s)
            sys.stdout.flush()

    def print_title(self, s):
        """
        Format and print title.
        e.g.
        =====
        Title
        =====

        Inputs:
            s (str): Title
        Outputs:
            None
        """
        self._write('\n')
        self._write('%s\n' % ('=' * len(s)))
        self._write('%s\n' % s.upper())
        self._write('%s\n' % ('=' * len(s)))
        self._write('\n')

    def print_section(self, s):
        """
        Format and print section title.
        e.g.
        Section
        -------

        Inputs:
            s (str): Section title
        Outputs:
            None
        """
        self._write('\n')
        self._write('%s\n' % s)
        self._write('%s\n' % ('-' * len(s)))
        self._write('\n')

    def print_sub_section(self, s, level=0):
        """
        Format and print sub-section title.
        e.g.
        [-]+ Sub-section

        Inputs:
            s (str): Sub-section title
            level (int): Sub-section level`
        Outputs:
            None
        """
        self._write('\n')
        self._write('%s+ %s\n' % ('-' * level, s))
        self._write('\n')

    def print_string(self, s):
        """
        Format and print a string.

        Inputs:
            s (str): String
        Outputs:
            None
        """
        self._write('%s\n' % s)

    def print_paragraph(self, p):
        """
        Format and print a paragraph.

        Inputs:
            p (str): Paragraph
        Outputs:
            None
        """
        self._write('%s\n\n' % p)

    def print_newline(self):
        """
        Print newline.

        Inputs:
            None
        Outputs:
            None
        """
        self._write('\n')

    def __exit__(self):
        # Close file
        if fh is not sys.stdout:
            self.fh.close()


def hostname():
    """
    Return the system hostname.

    Inputs:
        None
    Outputs:
        hostname (str): System hostname
    """
    if collector:
        retcode, hostname = execute("cat %s/network/nodename" % collector)
    else:
        retcode, hostname = execute("hostname")
    if retcode:
        log("ERROR", "failed to get system hostname")
        log("ERROR", output)
        sys.exit(1)

    return hostname


def rsf_partner():
    """
    Return cluster partner hostname.

    Inputs:
        None
    Outputs:
        partner (str): Partner hostname
    """
    rsfcli = "/opt/HAC/RSF-1/bin/rsfcli -i0"
    hname = hostname()
    partner = None
    hosts = []
    name = None

    # First try to determine if the cluster is configured.
    # 4.x makes determination tricky because the service is installed
    # and running by default.

    # Make sure services are running
    try:
        retcode, output = execute("%s isrunning" % rsfcli)
    except Exception, err:
        log("ERROR", "unable to determine RSF service state")
        log("ERROR", output)
        sys.exit(1)

    # Non-zero return code means service is not running
    if retcode:
        log("INFO", "RSF service is not running")
        return partner

    log("INFO", "RSF service is running")

    # Parse the RSF status
    retcode, output = execute("/opt/HAC/RSF-1/bin/rsfcli status")
    for l in output.splitlines():
        if l.startswith("Contacted"):
            name = l.split()[4].rstrip(",").strip("\"")
        elif l.startswith("Host"):
            hosts.append(l.split()[1].strip())

    # Check for default 4.x configuration
    if name == "Ready_For_Cluster_Configuration":
        log("INFO", "Cluster is not configured")
        return partner

    log("INFO", "RSF cluster is configured")

    # Determine which clustered host is the partner
    for h in hosts:
        if h != hname:
            partner = h
            log("INFO", "%s is partner node" % partner)
            break

    return partner


def sections(section, level):
    """
    Iterate over a section.

    Inputs:
        section
        level
    Outputs:
        None
    """
    # Valid keys
    valid = ["title", "enabled", "paragraph", "cmd", "nmc", "sections",
             "collector"]
    # Required keys
    required = ["title", "enabled"]

    # Iterate over each sub-section
    for subsection in section:
        # Verify required keys are present
        for key in required:
            if key not in subsection:
                log("ERROR", "Required key \"%s\" missing" % key)
                sys.exit(1)

        # Verify there are no unsupported keys present
        for key in subsection:
            if key not in valid:
                log("ERROR", "Invalid key \"%s\"" % key)
                sys.exit(1)

        # Continue if the section is disabled
        if not subsection["enabled"]:
            continue

        # Handle title
        title = subsection["title"]
        log("INFO", "Section \"%s\"" % title)
        if level == 0:
            sig.print_title(title)
        elif level == 1:
            sig.print_section(title)
        else:
            sig.print_sub_section(title, level-2)

        # Handle paragraph
        if "paragraph" in subsection:
            paragraph = subsection["paragraph"]
            if paragraph is not None:
                sig.print_paragraph(paragraph)

        # Handle collector fields: alternative to both cmd and nmc
        if collector:
            if "collector" in subsection:
                location = subsection["collector"]
                execute_collector(location, document)
            else:
                log("WARN", "Collector generation specified but section " \
                            "\"%s\" has no collector subsection" % title)
        else:
            # Handle command
            if "cmd" in subsection:
                cmd = subsection["cmd"]
                if cmd is not None:
                    execute_cmd(cmd)

            # Handle nmc
            if "nmc" in subsection:
                nmc = subsection["nmc"]
                if nmc is not None:
                    execute_nmc(nmc)

        # Handle sections
        if "sections" in subsection:
            sections(subsection["sections"], level + 1)


def main():
    # Initialize variables
    global sig
    global collector
    global ignore
    config = "autosig.conf"

    # Define the command line arguments
    try:
        opts, args = getopt.getopt(sys.argv[1:], ":hc:C:i",
                                   ["help", "config=", "collector=", "ignore"])
    except getopt.GetoptError, err:
        log("ERROR", str(err))
        usage()
        sys.exit(2)

    # Parse the command line arguments
    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit()
        elif o in ("-c", "--config"):
            config = a
        elif o in ("-C", "--collector"):
            collector = a
        elif o in ("-i", "--ignore"):
            ignore = True

    # Open the configuration file
    try:
        fh = open(config)
    except Exception, err:
        log("ERROR", "Cannot open the config file")
        log("ERROR", str(err))
        sys.exit(1)

    # Parse the configuration file
    try:
        outline = simplejson.load(fh, encoding=None, cls=None,
                                  object_hook=None)
    except Exception, err:
        log("ERROR", "Cannot parse the config file")
        log("ERROR", str(err))
        sys.exit(1)
    finally:
        fh.close()

    # Test existence to prevent confusing errors downstream
    if collector:
        if not os.path.isdir(collector):
            log("ERROR", "No collector directory '%s'" % collector)
            sys.exit(1)

    # Get hostnames initialize variables
    partner = rsf_partner()
    hname = hostname()

    # Open the output file
    if partner is None:
        f = "nexenta-autosig-%s.txt" % hname
    else:
        f = "nexenta-autosig-%s-%s.txt" % (hname, partner)
    sig = Document(f)
    log("INFO", "Writing output to %s" % f)

    # Write the version number
    sig.print_string("Version %s" % version)

    # Iterate over the document sections
    level = 0
    sections([outline], level)

    log("INFO", "Complete!")


if __name__ == "__main__":
    main()
