const fs = require('fs');
const path = require('path');
const file = path.join(__dirname, '..', 'frontend', 'index.html');
const html = fs.readFileSync(file,'utf8');
const regex = /<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi;
let m;
let i=0;
let errors=[];
while((m=regex.exec(html))!==null){
  i++;
  const code = m[1];
  try{
    new Function(code);
  }catch(e){
    errors.push({script:i,error:e.message});
  }
}
if(errors.length){
  console.error('SYNTAX_ERRORS', JSON.stringify(errors,null,2));
  process.exit(2);
}else{
  console.log('OK', i, 'inline scripts valid');
  process.exit(0);
}
