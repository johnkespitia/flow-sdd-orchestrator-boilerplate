FROM node:20-slim

RUN npm install -g pnpm

WORKDIR /app
