<html>
<body>
<h3>Estamos dentro del archivo registros</h3>
<table border="1">
        <tbody>
    <tr>
    <th id="Matricula">Matricula</th>
    <th id="Nombre">Nombre</th>
    <th id="Apellido paterno">Apellido paterno</th>
    <th id="Apellido materno">Apellido materno</th>
    <th id="Edad">Edad</th>
    <th id="Especialidad">Especialidad</th>
    <th id="Turno">Turno</th>
    <th id="Grupo">Grupo</th>
    <th id="Semestre">Semestre</th>
    </tr>

<?php
    $server = "sql207.byethost7.com";
    $usuario = "b7_30512558";
    $contrase = "123456";
    $bd = "b7_30512558_cetis132";

    $conexion = mysqli_connect($server, $usuario, $contrase, $bd)
    or die ("Error en la conexion");

       $matricu = $_POST['txtMatricula'];

    global $mysql;
    $consulta = mysqli_query($conexion, "SELECT * FROM estudiantes WHERE NumControl='$matricu' ")
    or die ("Error al traer los datos".mysqli_error($conexion));
    
echo'<h2>Se creo y ejecuto la consulta</h2>';

        echo'<h3>Esta es la matricula : </h3>'.$matricu;
    
    if($consulta){

        echo'<h3>Esta es la matricula : </h3>'.$matricu;

    while($extraido = mysql_fetch_row($consulta)){
        echo'Este es el resultado encontrado';



        ?>

        <tr>
        <td><?php echo $extraido[0];?></td>
        <td><?php echo $extraido[1];?></td>
        <td><?php echo $extraido[2];?></td>
        <td><?php echo $extraido[3];?></td>
        <td><?php echo $extraido[4];?></td>
        <td><?php echo $extraido[5];?></td>
        <td><?php echo $extraido[6];?></td>
        <td><?php echo $extraido[7];?></td>
        <td><?php echo $extraido[8];?></td>
        </tr>

        <?php
    }

    }else{
        echo'No se encontro ningun dato';
        echo'<h2>Estamos en else</h2>';
    }

    mysqli_close($conexion);
    echo'</table>';
echo'<h2>Fin del ejercicio</h2>';
    ?>
    <input type="button" onclick="history.back()" name="volver atrás" value="volver atrás">
    </body>
    </html>