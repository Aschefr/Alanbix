FROM node:20-alpine

WORKDIR /app

COPY package.json ./
# package-lock.json will be copied if it exists, otherwise just package.json
COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]
