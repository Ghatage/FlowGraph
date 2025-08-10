#!/usr/bin/env python3
"""
GitHub Issue and Solution Extractor

This script pulls GitHub issue details and finds the associated PR that solved it.
Requires a GitHub personal access token for API access.
"""

import requests
import re
import json
import argparse
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse


class GitHubExtractor:
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitHub-Issue-Extractor'
        }
        self.base_url = 'https://api.github.com'
    
    def get_issue(self, owner: str, repo: str, issue_number: int) -> Dict:
        """Fetch issue details from GitHub API."""
        url = f'{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}'
        response = requests.get(url, headers=self.headers)
        
        if response.status_code == 404:
            raise Exception(f"Issue #{issue_number} not found in {owner}/{repo}")
        elif response.status_code != 200:
            raise Exception(f"API request failed: {response.status_code} - {response.text}")
        
        return response.json()
    
    def get_issue_comments(self, owner: str, repo: str, issue_number: int) -> List[Dict]:
        """Fetch all comments for an issue."""
        url = f'{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}/comments'
        comments = []
        page = 1
        
        while True:
            response = requests.get(
                url, 
                headers=self.headers,
                params={'page': page, 'per_page': 100}
            )
            
            if response.status_code != 200:
                break
                
            page_comments = response.json()
            if not page_comments:
                break
                
            comments.extend(page_comments)
            page += 1
        
        return comments
    
    def get_issue_events(self, owner: str, repo: str, issue_number: int) -> List[Dict]:
        """Fetch issue events (including cross-references)."""
        url = f'{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}/events'
        response = requests.get(url, headers=self.headers)
        
        if response.status_code == 200:
            return response.json()
        return []
    
    def get_pr(self, owner: str, repo: str, pr_number: int) -> Dict:
        """Fetch PR details from GitHub API."""
        url = f'{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}'
        response = requests.get(url, headers=self.headers)
        
        if response.status_code == 200:
            return response.json()
        return {}
    
    def extract_pr_references(self, text: str, owner: str, repo: str) -> List[int]:
        """Extract PR numbers from text using various patterns."""
        pr_numbers = []
        
        # Pattern 1: #123 format
        hashtag_pattern = r'#(\d+)'
        matches = re.findall(hashtag_pattern, text)
        pr_numbers.extend([int(match) for match in matches])
        
        # Pattern 2: Full GitHub PR URLs
        url_pattern = rf'https://github\.com/{re.escape(owner)}/{re.escape(repo)}/pull/(\d+)'
        matches = re.findall(url_pattern, text)
        pr_numbers.extend([int(match) for match in matches])
        
        # Pattern 3: "closes #123", "fixes #123", etc.
        closing_pattern = r'(?:closes?|fixes?|resolves?)\s+#(\d+)'
        matches = re.findall(closing_pattern, text, re.IGNORECASE)
        pr_numbers.extend([int(match) for match in matches])
        
        return list(set(pr_numbers))  # Remove duplicates
    
    def find_solving_pr(self, owner: str, repo: str, issue_number: int) -> Optional[Dict]:
        """Find the PR that solved the issue."""
        issue = self.get_issue(owner, repo, issue_number)
        
        # Check if issue is closed
        if issue['state'] != 'closed':
            print(f"Warning: Issue #{issue_number} is still open")
        
        # Collect all potential PR references
        pr_candidates = []
        
        # Check issue body
        if issue['body']:
            pr_refs = self.extract_pr_references(issue['body'], owner, repo)
            pr_candidates.extend(pr_refs)
        
        # Check comments
        comments = self.get_issue_comments(owner, repo, issue_number)
        for comment in comments:
            if comment['body']:
                pr_refs = self.extract_pr_references(comment['body'], owner, repo)
                pr_candidates.extend(pr_refs)
        
        # Check events for cross-references
        events = self.get_issue_events(owner, repo, issue_number)
        for event in events:
            if event.get('event') == 'cross-referenced' and event.get('source'):
                if event['source'].get('type') == 'issue' and 'pull_request' in event['source']['issue']:
                    pr_url = event['source']['issue']['pull_request']['url']
                    pr_number = int(pr_url.split('/')[-1])
                    pr_candidates.append(pr_number)
            elif event.get('event') == 'closed' and event.get('commit_id'):
                # Issue was closed by a commit, try to find associated PR
                # This would require additional API calls to find PR from commit
                pass
        
        # Remove duplicates and validate PRs
        pr_candidates = list(set(pr_candidates))
        
        # Find the most likely solving PR
        solving_pr = None
        for pr_num in pr_candidates:
            pr = self.get_pr(owner, repo, pr_num)
            if pr and pr.get('state') == 'closed' and pr.get('merged'):
                # Check if PR mentions this issue
                pr_body = pr.get('body', '') or ''
                if f"#{issue_number}" in pr_body or str(issue_number) in pr_body:
                    # Check for closing keywords
                    closing_pattern = rf'(?:closes?|fixes?|resolves?)\s+#{issue_number}\b'
                    if re.search(closing_pattern, pr_body, re.IGNORECASE):
                        solving_pr = pr
                        break
                    elif not solving_pr:  # Keep as candidate if no better one found
                        solving_pr = pr
        
        return solving_pr
    
    def print_issue_and_solution(self, owner: str, repo: str, issue_number: int):
        """Main function to print issue details and solution."""
        try:
            print(f"{'='*80}")
            print(f"GITHUB ISSUE ANALYSIS: {owner}/{repo}#{issue_number}")
            print(f"{'='*80}")
            
            # Get issue details
            issue = self.get_issue(owner, repo, issue_number)
            
            print(f"\n📋 ISSUE DETAILS")
            print(f"{'─'*50}")
            print(f"Title: {issue['title']}")
            print(f"State: {issue['state']}")
            print(f"Created: {issue['created_at']}")
            print(f"Author: {issue['user']['login']}")
            print(f"URL: {issue['html_url']}")
            
            if issue.get('labels'):
                labels = [label['name'] for label in issue['labels']]
                print(f"Labels: {', '.join(labels)}")
            
            print(f"\n📝 ISSUE DESCRIPTION:")
            print(f"{'─'*50}")
            if issue['body']:
                print(issue['body'])
            else:
                print("(No description provided)")
            
            # Find solving PR
            print(f"\n🔍 SEARCHING FOR SOLUTION...")
            solving_pr = self.find_solving_pr(owner, repo, issue_number)
            
            if solving_pr:
                print(f"\n✅ SOLUTION FOUND")
                print(f"{'─'*50}")
                print(f"PR Title: {solving_pr['title']}")
                print(f"PR Number: #{solving_pr['number']}")
                print(f"State: {solving_pr['state']} ({'Merged' if solving_pr['merged'] else 'Not merged'})")
                print(f"Created: {solving_pr['created_at']}")
                print(f"Author: {solving_pr['user']['login']}")
                print(f"URL: {solving_pr['html_url']}")
                
                if solving_pr.get('merged_at'):
                    print(f"Merged: {solving_pr['merged_at']}")
                
                print(f"\n📝 PR DESCRIPTION:")
                print(f"{'─'*50}")
                if solving_pr['body']:
                    print(solving_pr['body'])
                else:
                    print("(No description provided)")
                
                # Show file changes summary
                if solving_pr.get('changed_files'):
                    print(f"\n📊 CHANGES SUMMARY:")
                    print(f"{'─'*50}")
                    print(f"Files changed: {solving_pr['changed_files']}")
                    print(f"Additions: +{solving_pr['additions']}")
                    print(f"Deletions: -{solving_pr['deletions']}")
            else:
                print(f"\n❌ NO CLEAR SOLUTION FOUND")
                print(f"{'─'*50}")
                print("Could not identify a PR that definitively solved this issue.")
                print("This might happen if:")
                print("- The issue was closed without a PR")
                print("- The solving PR doesn't reference this issue clearly")
                print("- The issue is still open")
            
        except Exception as e:
            print(f"❌ Error: {e}")


def parse_github_url(url: str) -> Tuple[str, str, int]:
    """Parse GitHub issue URL to extract owner, repo, and issue number."""
    # Handle both github.com URLs and just owner/repo#issue format
    if url.startswith('http'):
        parsed = urlparse(url)
        path_parts = parsed.path.strip('/').split('/')
        if len(path_parts) >= 4 and path_parts[2] == 'issues':
            owner, repo = path_parts[0], path_parts[1]
            issue_number = int(path_parts[3])
            return owner, repo, issue_number
    else:
        # Format: owner/repo#123
        if '#' in url:
            repo_part, issue_part = url.split('#')
            if '/' in repo_part:
                owner, repo = repo_part.split('/')
                issue_number = int(issue_part)
                return owner, repo, issue_number
    
    raise ValueError("Invalid GitHub URL or format. Use: owner/repo#123 or full GitHub URL")


def main():
    parser = argparse.ArgumentParser(description='Extract GitHub issue and solution details')
    parser.add_argument('issue', help='GitHub issue (format: owner/repo#123 or full URL)')
    parser.add_argument('--token', required=True, help='GitHub personal access token')
    
    args = parser.parse_args()
    
    try:
        owner, repo, issue_number = parse_github_url(args.issue)
        extractor = GitHubExtractor(args.token)
        extractor.print_issue_and_solution(owner, repo, issue_number)
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
