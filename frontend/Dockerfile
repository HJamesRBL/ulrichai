# Frontend Dockerfile for Production Deployment
# Multi-stage build for optimized production image
# Updated: Force cache bust for esbuild minifier fix

# Stage 1: Build
FROM node:20-alpine AS builder

# Set working directory
WORKDIR /app

# Copy package files
COPY package*.json ./

# Install all dependencies (including devDependencies needed for build)
# Force fresh install to bust cache
RUN npm ci --prefer-offline=false

# Clear npm cache to ensure fresh build
RUN npm cache clean --force

# Copy source code
COPY . .

# Remove any existing build directory
RUN rm -rf build

# Build argument for API URL
ARG REACT_APP_API_URL
ENV REACT_APP_API_URL=$REACT_APP_API_URL
ENV REACT_APP_ENVIRONMENT=production
ENV NODE_OPTIONS="--max-old-space-size=8192"

# Build the application fresh
RUN npm run build

# Stage 2: Production
FROM nginx:alpine

# Copy built files from builder
COPY --from=builder /app/build /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy startup script
COPY start-nginx.sh /start-nginx.sh
RUN chmod +x /start-nginx.sh

# Expose port (Railway will set PORT env var)
EXPOSE 80

# Start nginx with PORT support
CMD ["/start-nginx.sh"]
