#!/usr/bin/env python3

import json
import shlex
import shutil
import subprocess
import sys
import textwrap
import yaml

from pprint import pp, pformat

CONFIG_FILE = 'config.yaml'


def load_config_file():
	"""Comment"""
	try:
		return yaml.safe_load(open(CONFIG_FILE, 'r'))
	except Exception as e:
		print(e)


def do_govc_cmd(cmd="about", cmd_args=None):
	"""
	:param cmd:
	:param cmd_args:
	:return:
	"""
	cmdline = "/usr/local/bin/govc {cmd} -json {args}".format(cmd=cmd, args=cmd_args)
	print('Command : {}'.format(cmdline))
	proc = subprocess.Popen(
		shlex.split(cmdline),
		shell=False,
		bufsize=-1, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	(out, err) = proc.communicate()
	if err:
		try:
			fault = json.loads(err)
			if fault['Fault']:
				print(u'Error   : "{}"\nQuitting.'.format(fault['LocalizedMessage']))
			sys.exit(1)
		except json.decoder.JSONDecodeError:
			print(err.decode('utf-8'), file=sys.stderr, flush=True)
	if out != b'':
		reply = None
		try:
			reply = json.loads(out)
		except json.decoder.JSONDecodeError:
			reply = out.decode('utf-8')
		return reply


def main():
	"""Comment"""
	config_data = load_config_file()
	govc = config_data['govc_settings']

	# Can we successfully connect using govc?
	try:
		reply = do_govc_cmd(cmd='session.ls')
		if reply and reply['CurrentSession']:
			print('Session key found for: {}'.format(reply['CurrentSession']['UserName']))
	except Exception:
		raise

	for this_config in config_data['vm_list']:
		try:
			assert this_config['name'], "'name' not defined"
			assert this_config['src'], "'src' not defined"
			assert this_config['guest_type'], "'guest_type' not defined"
			assert this_config['udid'], "'udid' not defined"
		# TODO: if 'folder' defined assert it exists
		except AssertionError as e:
			print('Configuration file error: {}\nQuitting.'.format(e))
			sys.exit(1)

		if 'disabled' in this_config and this_config['disabled'] is True:
			print('Skipping {vm} because disabled flag is set.'.format(
				vm=this_config['name']))
			continue

		# assert that vm with defined name exists and has 'green' status
		try:
			result = do_govc_cmd('vm.info', '"{vm}"'.format(vm=this_config['src']))
			assert result['VirtualMachines'] is not None, "VM not found"
			assert result['VirtualMachines'][0]['OverallStatus'] == "green", \
				'VM "{vm}" exists but overall status is {status} (not green).'.format(
					vm=this_config['src'],
					status=result['VirtualMachines'][0]['OverallStatus']
				)
		except AssertionError as e:
			print('Error querying status of vm "{}" : {}'.format(
				this_config['src'], e))
			print('this_config == {}\nQuitting.'.format(
				pformat(this_config, width=72, indent=2)),
				flush=True)
			sys.exit(1)

		# TODO: Create clone of 'src' VM
		#       govc vm.clone -vm="$src" -link=true -snapshot="Initial import" -on=false -folder="ade-mdm" -force=true "$name"
		do_govc_cmd(
			'vm.clone',
			'-vm "{src}" '
			'-link="{link}" '
			'-snapshot="{snapshot}" '
			'-on="{on}" '
			'-folder="{folder}" '
			'-force="{force}" '
			'-ds={ds} '
			'-pool={pool} '
			'"{name}"'.format(
				src=this_config['src'],
				link=True,
				snapshot="Initial import",
				on=False,
				folder=govc['folder'],
				force=True,
				ds=govc['ds'],
				pool=govc['pool'],
				name=this_config['name']))
		# TODO: Fix vm.clone error: default datastore resolves to multiple instances, please specify
		# TODO: Handle 'result' which returns empty (and value 0) on success, but JSON object with key 'Fault' on error

		# Set guest os type for vm
		# Enum - VirtualMachineGuestOsIdentifier(vim.vm.GuestOsDescriptor.GuestOsIdentifier)
		# See also: https://bit.ly/3Md7qec
		do_govc_cmd('vm.change', '-vm "{vm}" -g "{os}"'.format(
			vm=this_config['name'],
			os=this_config['guest_type']))

		#
		# ╺┳┓┏━┓   ┏┓╻┏━┓╺┳╸   ┏━╸╻ ╻┏━┓┏┓╻┏━╸┏━╸   ┏┓ ┏━┓┏━┓┏━╸╻  ╻┏┓╻┏━╸   ╻ ╻┏┳┓┏━┓
		#  ┃┃┃ ┃   ┃┗┫┃ ┃ ┃    ┃  ┣━┫┣━┫┃┗┫┃╺┓┣╸    ┣┻┓┣━┫┗━┓┣╸ ┃  ┃┃┗┫┣╸    ┃┏┛┃┃┃┗━┓
		# ╺┻┛┗━┛   ╹ ╹┗━┛ ╹    ┗━╸╹ ╹╹ ╹╹ ╹┗━┛┗━╸   ┗━┛╹ ╹┗━┛┗━╸┗━╸╹╹ ╹┗━╸   ┗┛ ╹ ╹┗━┛
		# ┏━┓┏┓╻╻  ╻ ╻   ┏━╸╻  ┏━┓┏┓╻┏━╸┏━┓
		# ┃ ┃┃┗┫┃  ┗┳┛   ┃  ┃  ┃ ┃┃┗┫┣╸ ┗━┓
		# ┗━┛╹ ╹┗━╸ ╹    ┗━╸┗━╸┗━┛╹ ╹┗━╸┗━┛
		#
		# IFF the VM is a clone
		#    How to tell if it is?
		#     - Nothing in vm.info -json output appears to indicate this
		#      - Name? Ex. "macOS-11.6.6-20G624" vs "macOS-11.6.6-20G624--C07N50HKDY3J"
		#      - Folder? "ade-mdm" vs "mac-lab"
		#      - macos_src_vm (the config_data key) ends with a string like "_jamf" or "_mdm"?
		#
		# Set bios uuid (aka Apple Hardware UDID)
		# For Apple ADE and MDM testing this must be carefully considered
		#   (ex. Jamf uses this + serial number to track distinct Computer records)
		do_govc_cmd('vm.change', '-vm "{vm}" -uuid "{uuid}"'.format(
			vm=this_config['name'],
			uuid=this_config['udid']))
		# Set vmx extra configuration parameters
		extra_config_args = ['-vm {vm}'.format(vm=this_config['name'])]
		for key, value in this_config['extra_config'].items():
			# TODO: Ensure that a $key.reflectHost = "FALSE" set for 'board-id', 'hw.model', and 'serial.number' (actually is this even necessary for ESXi/vSphere?)
			extra_config_args.append('-e "{key}={value}"'.format(key=key, value=value))
		do_govc_cmd('vm.change', ' '.join(extra_config_args))

		# TODO: Ensure CD/DVD device exists but has no volumes configured
		#       govc device.info -json -vm $name "cdrom*"
		#       Note: Exits with 1 and stdout text (ex.'govc: device 'cdrom*' not found')
		#       Note: Every time above add command run will add another cdrom, so check first!
		result = do_govc_cmd('device.info', '-vm "{vm}" "cdrom*"'.format(vm=this_config['name']))
		if not result:
			# govc device.cdrom.add -vm $name  #=> 'cdrom-3000'
			do_govc_cmd('device.cdrom.add', '-vm "{vm}"'.format(vm=this_config['name']))
		else:
			print('Device {} found.'.format(result['Devices'][0]['Name']))
		# TODO: Ensure ethernet connected
		#       govc device.ls -json -vm $name \
		#       | jq -r '.Devices|map(select(.Name|contains("ethernet")))[].Name' \
		#       | while read -r NIC
		#         do
		#           govc device.connect -vm $name "$NIC"
		#           govc vm.network.change -vm $name -net="VM Network" -net.adapter="vmxnet3" "$NIC"
		#         done
		#
		# TODO: Create an initial snapshot of new linked clone
		#       govc snapshot.create -vm "$name" "linked clone created"


if __name__ == '__main__':
	banner = """
╻ ╻┏━┓┏━┓╻ ╻┏━╸┏━┓┏━╸   ┏┳┓┏━┓┏━╸┏━┓┏━┓   ╺┳╸┏━╸┏┳┓┏━┓╻  ┏━┓╺┳╸╻┏┓╻┏━╸
┃┏┛┗━┓┣━┛┣━┫┣╸ ┣┳┛┣╸    ┃┃┃┣━┫┃  ┃ ┃┗━┓    ┃ ┣╸ ┃┃┃┣━┛┃  ┣━┫ ┃ ┃┃┗┫┃╺┓
┗┛ ┗━┛╹  ╹ ╹┗━╸╹┗╸┗━╸   ╹ ╹╹ ╹┗━╸┗━┛┗━┛    ╹ ┗━╸╹ ╹╹  ┗━╸╹ ╹ ╹ ╹╹ ╹┗━┛
	"""
	disclaimer = """\
This program assumes that you have already built the base macOS VMs properly, uploaded them to vSphere/ESXi, and created an initial snapshot labeled "Initial import".
	"""
	overview = """\
This program takes an existing, clean-installed macOS VM, performed with virtual ethernet device(s) disconnected, and which was shut down before Install Assistant was run. It loads the YAML configuration file, then for _each_ defined source macOS VM ('src'):
	"""
	steps = """
0. Checks whether a VM named $name [in folder $folder? (which is not defined as a configuration key)] exists, and if so then what? Stop and ask? Skip?
1. Checks that 'name', 'src', and 'guest_type' are defined at a minimum
2. Verifies that 'src' VM exists # TODO: determine how deeply is this checked
3. Ensures that 'src' VM’s defined guest os identifier is set in vSphere
4. … 
	"""
	# width = shutil.get_terminal_size().columns
	# print(banner)
	# print(textwrap.fill(disclaimer, width=width, expand_tabs=False))
	# print('')
	# print(textwrap.fill(overview, width=width, expand_tabs=False))
	# print(steps)
	# if input("Do You Want To Continue? [yes/N] ") == "yes":
	# 	main()
	main()