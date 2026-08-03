FROM node:20-alpine

WORKDIR /app

# Copy package files from the build context (frontend/) into the image
COPY package.json package-lock.json ./
RUN npm install -g pnpm && pnpm install

# Copy the rest of the frontend source
COPY . .

ENV NODE_ENV=development

CMD ["pnpm", "dev", "--hostname", "0.0.0.0", "--port", "3000"]