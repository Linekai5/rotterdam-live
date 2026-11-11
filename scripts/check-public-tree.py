#!/usr/bin/env python3
"""Check the current tracked files. This does not sanitize repository history."""

import ipaddress
from pathlib import Path
import re
import subprocess
import sys


DOC_SUFFIXES = {'.md', '.markdown', '.mdown', '.mdx', '.rst', '.txt'}
IPV4 = re.compile(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])')
IPV6 = re.compile(r'(?<![\w:])(?:[a-fA-F\d]{0,4}:){2,}[a-fA-F\d:.]*(?:%[\w.-]+)?')
SECRETS = {
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----'),
    'access token': re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{32,}|xox[baprs]-[A-Za-z0-9-]{20,})'),
    'hardcoded credential default': re.compile(r'\$\{\w*(?:PASSWORD|SECRET|TOKEN|API_KEY):-([^}]+)\}', re.I),
    'credential URL': re.compile(r'[a-z][a-z0-9+.-]*://[^\s/:@]+:([^\s/@]+)@', re.I),
    'credential assignment': re.compile(r'^\s*(?:export\s+)?[\w.-]*(?:PASSWORD|SECRET|TOKEN|API_KEY)\s*[:=]\s*([^\r\n#]+)', re.I),
}


def check_text(name, content):
    findings = []
    for number, line in enumerate(content.splitlines(), 1):
        if Path(name).suffix.lower() in DOC_SUFFIXES:
            for match in (*IPV4.finditer(line), *IPV6.finditer(line)):
                try:
                    ipaddress.ip_address(match.group())
                except ValueError:
                    continue
                findings.append(f'{name}:{number}: IP literal in documentation')
        for label, pattern in SECRETS.items():
            for match in pattern.finditer(line):
                # Environment interpolation is configuration, not a literal credential.
                if label == 'credential URL' and any(char in match.group(1) for char in '${}'):
                    continue
                if label == 'credential assignment':
                    value = match.group(1).strip().strip('\'"')
                    if not value or value.startswith('${'):
                        continue
                findings.append(f'{name}:{number}: {label}')
    return findings


def main():
    root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip())
    files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    ignored = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--ignored', '--exclude-standard', '-z'], cwd=root
    ).decode().split('\0')
    findings = [f'{name}: tracked file matches an ignore rule' for name in ignored if name]
    for name in filter(None, files):
        if name.startswith(('api/', '.agents/', '.gemini/')) or name == '.github/workflows/deploy.yml':
            findings.append(f'{name}: private path is tracked')
        try:
            content = (root / name).read_text()
        except UnicodeError:
            continue
        except OSError:
            findings.append(f'{name}: tracked file cannot be read')
            continue
        findings.extend(check_text(name, content))
    if findings:
        print('\n'.join(sorted(set(findings))))
        print('Public-tree check failed. Values are intentionally omitted.')
        return 1
    print('Public-tree check passed. Historical commits were not checked or changed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
