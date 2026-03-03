<?php 
    
    $server = "localhost";
    $usuario = "root";
    $contrasena = "";
    $bd = "cetis no. 132";

    $conexion = mysqli_connect($server, $usuario, $contrasena, $bd)
    or die ("Error en la conexion");

    $matricula = $_POST['txtMatricula'];
    $nombre = $_POST['txtNombre'];
    $apellido_paterno = $_POST['txtApellido_paterno'];
    $apellido_materno = $_POST['txtApellido_materno'];
    $edad = $_POST['txtEdad'];
    $especialidad = $_POST['cmbEspecialidad'];
    $turno = $_POST['cmbTurno'];
    $grupo = $_POST['cmbGrupo'];
    $semestre = $_POST['cmbSemestre'];

    mysqli_query($conexion, "UPDATE tabla_estudiantes set nombre='$nombre', '$apellido_paterno', '$apellido_materno', 
    '$edad', '$especialidad', '$turno', '$grupo', '$semestre'  where Matrícula='$matricula'")
    or die("Error al actualizar");

mysqli_close($conexion);
echo"Datos actualizado correctamente";
    ?>
    <html>
    <input type="button" onclick="history.back()" name="volver atrás" value="volver atrás">
    </html>