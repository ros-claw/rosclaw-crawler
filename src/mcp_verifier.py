#!/usr/bin/env python3
"""
MCP Verifier - Validates if a GitHub repository is a genuine MCP Server
"""

import os
import json
import urllib.request
import base64
import sqlite3
from datetime import datetime

class MCPVerifier:
    def __init__(self, github_token=None):
        self.github_token = github_token or os.getenv('GITHUB_TOKEN', '')
        self.headers = {
            'Accept': 'application/vnd.github.v3+json',
            'Authorization': f'token {self.github_token}',
            'User-Agent': 'rosclaw-mcp-verifier'
        }
    
    def verify_repo(self, owner, repo):
        """Verify if repository implements MCP protocol"""
        score = 0
        details = {
            'has_mcp_server_py': False,
            'has_claude_json': False,
            'has_readme_mcp': False,
            'mentions_mcp_protocol': False,
            'mentions_stdio': False,
            'mentions_sse': False,
            'mentions_tools': False,
            'has_package_json_mcp': False,
            'has_pyproject_mcp': False,
            'has_requirements_mcp': False,
        }
        
        try:
            # Check README
            req = urllib.request.Request(
                f'https://api.github.com/repos/{owner}/{repo}/readme',
                headers=self.headers
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                readme = base64.b64decode(data.get('content', '')).decode('utf-8', errors='ignore').lower()
            
            # Score README content
            if 'model context protocol' in readme:
                score += 3
                details['mentions_mcp_protocol'] = True
            if 'mcp server' in readme or 'mcp-server' in readme:
                score += 2
                details['has_readme_mcp'] = True
            if 'stdio' in readme:
                score += 1
                details['mentions_stdio'] = True
            if 'sse' in readme or 'server-sent' in readme:
                score += 1
                details['mentions_sse'] = True
            if 'tools' in readme and 'mcp' in readme:
                score += 1
                details['mentions_tools'] = True
                
        except:
            pass
        
        try:
            # Check repo contents
            req = urllib.request.Request(
                f'https://api.github.com/repos/{owner}/{repo}/contents',
                headers=self.headers
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                contents = json.loads(resp.read().decode())
            
            files = [item['name'].lower() for item in contents if item['type'] == 'file']
            
            if 'mcp_server.py' in files or 'server.py' in files:
                score += 3
                details['has_mcp_server_py'] = True
            if 'claude.json' in files or 'claude_desktop_config.json' in files:
                score += 3
                details['has_claude_json'] = True
            if 'package.json' in files:
                score += 1
                details['has_package_json_mcp'] = True
            if 'pyproject.toml' in files or 'setup.py' in files:
                score += 1
                details['has_pyproject_mcp'] = True
            if 'requirements.txt' in files:
                score += 1
                details['has_requirements_mcp'] = True
                
        except:
            pass
        
        # Determine status
        if score >= 5:
            status = 'verified'
        elif score >= 2:
            status = 'suspicious'
        else:
            status = 'not_mcp'
        
        return {
            'score': score,
            'status': status,
            'details': details
        }
    
    def verify_database(self, db_path):
        """Verify all MCPs in database"""
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        c.execute("SELECT full_name, stars FROM mcps WHERE decision='keep' ORDER BY stars DESC")
        mcps = c.fetchall()
        
        results = {
            'verified': [],
            'suspicious': [],
            'not_mcp': []
        }
        
        for name, stars in mcps:
            if '/' not in name:
                continue
            
            owner, repo = name.split('/', 1)
            result = self.verify_repo(owner, repo)
            
            # Save to verification table
            c.execute("""
                INSERT OR REPLACE INTO mcp_verification 
                (full_name, verified_at, verification_score, has_mcp_server_py, 
                 has_claude_json, has_readme_mcp, mentions_mcp_protocol, 
                 mentions_stdio, mentions_tools, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name, datetime.now().isoformat(), result['score'],
                result['details']['has_mcp_server_py'],
                result['details']['has_claude_json'],
                result['details']['has_readme_mcp'],
                result['details']['mentions_mcp_protocol'],
                result['details']['mentions_stdio'],
                result['details']['mentions_tools'],
                result['status']
            ))
            
            if result['status'] == 'verified':
                results['verified'].append((name, stars, result['score']))
            elif result['status'] == 'suspicious':
                results['suspicious'].append((name, stars, result['score']))
            else:
                results['not_mcp'].append((name, stars, result['score']))
        
        conn.commit()
        conn.close()
        
        return results

if __name__ == '__main__':
    verifier = MCPVerifier()
    print("MCP Verifier initialized")
    print("Usage: verifier.verify_repo('owner', 'repo')")
