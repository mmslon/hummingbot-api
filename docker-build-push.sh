#!/bin/bash

# Docker Build and Push Script
# Usage: ./docker-build-push.sh [tag_name] [dockerfile_path]

set -e  # Exit on any error

# Configuration
DOCKER_REPO="sadornik/api"
DEFAULT_TAG="latest"
DEFAULT_DOCKERFILE="Dockerfile"

# Parse arguments
TAG_NAME=${1:-$DEFAULT_TAG}
DOCKERFILE_PATH=${2:-$DEFAULT_DOCKERFILE}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    print_error "Docker is not running or not accessible. Please start Docker and try again."
    exit 1
fi

# Check if Dockerfile exists
if [[ ! -f "$DOCKERFILE_PATH" ]]; then
    print_error "Dockerfile not found at: $DOCKERFILE_PATH"
    exit 1
fi

# Build the Docker image
print_status "Building Docker image: $DOCKER_REPO:$TAG_NAME"
print_status "Using Dockerfile: $DOCKERFILE_PATH"

if docker build -f "$DOCKERFILE_PATH" -t "$DOCKER_REPO:$TAG_NAME" .; then
    print_success "Docker image built successfully!"
else
    print_error "Failed to build Docker image"
    exit 1
fi

# Ask for confirmation before pushing (optional - remove if you want automatic push)
print_warning "About to push $DOCKER_REPO:$TAG_NAME to Docker Hub"
read -p "Do you want to continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warning "Push cancelled by user"
    exit 0
fi

# Check if user is logged in to Docker Hub
if ! docker info | grep -q "Username:"; then
    print_warning "You don't appear to be logged in to Docker Hub"
    print_status "Attempting to log in..."
    if ! docker login; then
        print_error "Failed to log in to Docker Hub"
        exit 1
    fi
fi

# Push the image to Docker Hub
print_status "Pushing image to Docker Hub: $DOCKER_REPO:$TAG_NAME"

if docker push "$DOCKER_REPO:$TAG_NAME"; then
    print_success "Successfully pushed $DOCKER_REPO:$TAG_NAME to Docker Hub!"
else
    print_error "Failed to push image to Docker Hub"
    exit 1
fi

# Optional: Also tag and push as 'latest' if not already
if [[ "$TAG_NAME" != "latest" ]]; then
    read -p "Also tag and push as 'latest'? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_status "Tagging as latest and pushing..."
        docker tag "$DOCKER_REPO:$TAG_NAME" "$DOCKER_REPO:latest"
        docker push "$DOCKER_REPO:latest"
        print_success "Also pushed as latest!"
    fi
fi

print_success "Build and push completed successfully!"
print_status "Image available at: https://hub.docker.com/r/$DOCKER_REPO"