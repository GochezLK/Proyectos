
function ir(){
var usuario ="Rogelio_Cervantes_Hernandez";
var contraseña = "cetis132_oficial";

if(document.form.txtpassword.value==contraseña && document.form.txtusuario.value==usuario){
    alert ("Bienvenido :)");
    window.location='indexff.html';
}else{
    alert("Porfavor introdusca usuario y contraeña correcta");
}
}