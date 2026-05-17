const http = require('http');

const options = {
  hostname: 'localhost',
  port: 8000,
  path: '/tournaments',
  method: 'GET'
};

const req = http.request(options, (res) => {
  let data = '';
  res.on('data', (chunk) => {
    data += chunk;
  });
  res.on('end', () => {
    console.log("Raw Response:");
    console.log(data);
    
    try {
      const parsed = JSON.parse(data);
      console.log("\nParsed Array Length:", parsed.length);
      if (parsed.length > 0) {
        console.log("First element game_id type:", typeof parsed[0].game_id);
        console.log("First element game_id value:", parsed[0].game_id);
      }
    } catch (e) {}
  });
});

req.end();
