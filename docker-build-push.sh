#!/bin/bash
# Usage: ./docker-build-push.sh [tag_name] [dockerfile_path]
set -e  # Exit on any error

# Configuration
DOCKER_REPO="sadornik/api"
DEFAULT_TAG="latest"
DEFAULT_DOCKERFILE="Dockerfile"
PLATFORMS="linux/amd64,linux/arm64"  # Add more platforms if needed: linux/arm/v7

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

# Check if buildx is available
if ! docker buildx version > /dev/null 2>&1; then
    print_error "Docker buildx is not available. Please update Docker to a newer version."
    exit 1
fi

# Create and use a new builder instance if it doesn't exist
BUILDER_NAME="multiplatform-builder"
if ! docker buildx inspect "$BUILDER_NAME" > /dev/null 2>&1; then
    print_status "Creating new buildx builder: $BUILDER_NAME"
    docker buildx create --name "$BUILDER_NAME" --use
    print_success "Builder created successfully!"
else
    print_status "Using existing builder: $BUILDER_NAME"
    docker buildx use "$BUILDER_NAME"
fi

# Bootstrap the builder (ensures QEMU is set up)
print_status "Bootstrapping builder..."
docker buildx inspect --bootstrap

# Check if user is logged in to Docker Hub
if ! docker info | grep -q "Username:"; then
    print_warning "You don't appear to be logged in to Docker Hub"
    print_status "Attempting to log in..."
    if ! docker login; then
        print_error "Failed to log in to Docker Hub"
        exit 1
    fi
fi

# Ask for confirmation before building and pushing
print_warning "About to build and push $DOCKER_REPO:$TAG_NAME for platforms: $PLATFORMS"
read -p "Do you want to continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warning "Build cancelled by user"
    exit 0
fi

# Build and push multi-platform image
print_status "Building multi-platform Docker image: $DOCKER_REPO:$TAG_NAME"
print_status "Using Dockerfile: $DOCKERFILE_PATH"
print_status "Target platforms: $PLATFORMS"

if docker buildx build \
    --platform "$PLATFORMS" \
    -f "$DOCKERFILE_PATH" \
    -t "$DOCKER_REPO:$TAG_NAME" \
    --push \
    .; then
    print_success "Multi-platform Docker image built and pushed successfully!"
else
    print_error "Failed to build and push Docker image"
    exit 1
fi

# Optional: Also tag and push as 'latest' if not already
if [[ "$TAG_NAME" != "latest" ]]; then
    read -p "Also tag and push as 'latest'? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_status "Building and pushing as latest..."
        docker buildx build \
            --platform "$PLATFORMS" \
            -f "$DOCKERFILE_PATH" \
            -t "$DOCKER_REPO:latest" \
            --push \
            .
        print_success "Also pushed as latest!"
    fi
fi

print_success "Multi-platform build and push completed successfully!"
print_status "Image available at: https://hub.docker.com/r/$DOCKER_REPO"
print_status "Supported platforms: $PLATFORMS"

# Show image details
print_status "Verifying multi-platform manifest..."
docker buildx imagetools inspect "$DOCKER_REPO:$TAG_NAME"