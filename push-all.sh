#!/bin/bash
# Script to push to both Bitbucket and GitHub repositories

# Push to Bitbucket (origin)
echo "Pushing to Bitbucket..."
git push origin "$@"

# Push to GitHub
echo "Pushing to GitHub..."
git push github "$@"

echo "All pushes completed!"
