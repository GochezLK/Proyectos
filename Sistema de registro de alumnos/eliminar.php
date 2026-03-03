<?php 
    
    $server = "localhost";
    $usuario = "root";
    $contrasena = "";
    $bd = "cetis no. 132";

    $conexion = mysqli_connect($server, $usuario, $contrasena, $bd)
    or die ("Error en la conexion");
    
    $matricu = $_POST['txtMatricula'];

mysqli_query($conexion, "DELETE from tabla_estudiantes where Matrícula='$matricu'")
or die("Error al eliminar los datos");

mysqli_close($conexion);
echo"Datos eliminados correctamente"; 


    ?>
    <html>
    <input type="button" onclick="history.back()" name="volver atrás" value="volver atrás">
    </html>