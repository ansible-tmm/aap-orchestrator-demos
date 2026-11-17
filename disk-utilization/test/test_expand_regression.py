"""Run the expand playbook with mocked AWS and disk commands, never real infrastructure."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

import yaml

PLAYBOOKS = Path(__file__).resolve().parents[1] / 'playbooks'


class ExpandRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='disk-expand-test-')
        self.path = Path(self.tmp.name)
        shutil.copytree(PLAYBOOKS, self.path / 'playbooks')
        self.playbook = self.path / 'playbooks' / 'remediate_disk_expand.yml'
        plays = yaml.safe_load(self.playbook.read_text())
        plays[0]['gather_facts'] = False
        discovery = next(t for t in plays[0]['tasks'] if t['name'] == 'Discover EC2 instance identity')
        discovery.pop('ansible.builtin.include_tasks')
        discovery['ansible.builtin.set_fact'] = {'discovered_ec2_instance_id': 'i-test', 'discovered_aws_region': 'us-east-2'}
        block = plays[1]['tasks'][0]['block']
        fixtures = {
            'Gather EC2 instance info': ('amazon.aws.ec2_instance_info', '_instance_info',
                {'instances': [{'block_device_mappings': [{'device_name': '/dev/sda1', 'ebs': {'volume_id': 'vol-test'}}]}]}),
            'Gather current EBS volume info': ('amazon.aws.ec2_vol_info', '_volume_info', {'volumes': [{'size': 20}]}),
            'Expand EBS volume': ('amazon.aws.ec2_vol', '_volume_modify', {'changed': True}),
            'Wait for EBS volume modification to complete': ('amazon.aws.ec2_vol_info', '_volume_wait',
                {'volumes': [{'size': 25, 'modification_state': {'state': 'completed'}}]}),
        }
        for task in block:
            if task['name'] in fixtures:
                module, var, value = fixtures[task['name']]
                task.pop(module)
                task.pop('register', None)
                task.pop('until', None)
                task.pop('retries', None)
                task.pop('delay', None)
                task['ansible.builtin.set_fact'] = {var: value}
        plays[2]['become'] = False
        plays[2]['tasks'].append({'name': 'Check expected expansion facts', 'ansible.builtin.assert': {'that': [
            'volume_size_before_gb | int == 20', 'volume_size_after_gb | int == 25',
            "ec2_volume_id == 'vol-test'", "discovered_ec2_instance_id == 'i-test'",
        ]}})
        self.playbook.write_text(yaml.safe_dump(plays, sort_keys=False))
        bindir = self.path / 'bin'
        bindir.mkdir()
        commands = {
            'findmnt': 'echo /dev/nvme0n1p4',
            'lsblk': 'echo nvme0n1',
            'growpart': 'echo "$FAKE_GROWPART_OUTPUT"; exit "${FAKE_GROWPART_RC}"',
            'xfs_growfs': 'echo grown',
            'df': "printf 'Filesystem Type Size Used Avail Use%% Mounted on\\n/dev/nvme0n1p4 xfs 25G 10G 15G 40%% /\\n'",
        }
        for name, body in commands.items():
            p = bindir / name
            p.write_text('#!/bin/sh\n' + body + '\n')
            p.chmod(0o755)
        self.inventory = self.path / 'inventory.ini'
        self.inventory.write_text('[targets]\naws-rhel9 ansible_connection=local\nother-host ansible_connection=local\n')
        self.env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ['PATH'],
                        FAKE_GROWPART_OUTPUT='NOCHANGE: partition already full', FAKE_GROWPART_RC='1',
                        ANSIBLE_NOCOLOR='1')

    def tearDown(self):
        self.tmp.cleanup()

    def run_play(self, limit, expected=0):
        result = subprocess.run(['ansible-playbook', '-i', str(self.inventory), str(self.playbook), '--limit', limit],
                                env=self.env, text=True, capture_output=True, timeout=120)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def test_single_host_limit_runs_aws_and_accepts_nochange(self):
        output = self.run_play('aws-rhel9')
        self.assertIn('aws-rhel9 -> localhost', output)
        self.assertIn('Expanded vol-test on i-test (aws-rhel9) from 20 GiB to 25 GiB', output)
        self.assertIn('Check expected expansion facts', output)
        self.assertIn('Grow XFS filesystem on mount', output)

    def test_actual_growpart_error_fails_and_stops_before_xfs(self):
        self.env['FAKE_GROWPART_OUTPUT'] = 'FAILED: disk I/O error'
        output = self.run_play('aws-rhel9', expected=2)
        self.assertIn('FAILED: disk I/O error', output)
        self.assertNotIn('TASK [Grow XFS filesystem on mount]', output)

    def test_multiple_hosts_fail_before_aws(self):
        output = self.run_play('all', expected=2)
        self.assertIn('EBS expansion requires a limit selecting exactly one target host.', output)
        self.assertNotIn('TASK [Gather EC2 instance info]', output)


if __name__ == '__main__':
    unittest.main()
