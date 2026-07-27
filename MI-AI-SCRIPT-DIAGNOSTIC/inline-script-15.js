

(async()=>{

function currentUser(){

try{

if(window.firebase?.auth){
return firebase.auth().currentUser;
}

if(window.miFirebaseAuth){
return window.miFirebaseAuth.currentUser;
}

}catch(e){}

return null;

}

async function checkOwner(){

const u=currentUser();

if(!u)return;

const email=(u.email||"").toLowerCase();

if(email==="teamofchatbot.miai@gmail.com"){

const b=document.getElementById("chiefOwnerBtn");

if(b){

b.style.display="block";

b.onclick=function(){

location.href="/chief-owner";

};

}

}

}

setTimeout(checkOwner,1000);

})();

