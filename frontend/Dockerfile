FROM node:22-alpine

WORKDIR /app

# Install dependencies first (layer-cached)
COPY package.json ./
RUN npm install

# Copy source
COPY . .

# Expose Vite dev port
EXPOSE 5173

# Run Vite dev server bound to all interfaces (required for Docker port-mapping)
CMD ["npm", "run", "dev"]
