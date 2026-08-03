FROM node:20-alpine

WORKDIR /app

COPY frontend/package.json frontend/pnpm-lock.yaml* ./
RUN npm install -g pnpm && pnpm install

COPY frontend /app

ENV NODE_ENV=development

CMD ["pnpm", "dev", "--hostname", "0.0.0.0", "--port", "3000"]