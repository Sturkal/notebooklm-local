# Use official Node image
FROM node:22-alpine

# Set working directory
WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies (clean install to avoid esbuild version mismatch)
RUN npm ci --prefer-offline --no-audit

# Copy source code
COPY . .

# Expose port for Vite
EXPOSE 3000

# Start dev server
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]
