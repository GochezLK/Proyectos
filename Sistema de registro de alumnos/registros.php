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
    $server = "localhost";
    $usuario = "root";
    $contraseña = "";
    $bd = "cetis no. 132";

    $conexion = mysqli_connect($server, $usuario, $contraseña, $bd)
    or die ("Error en la conexion");

    $matricu = $_POST['txtMatricula'];

    $consulta = mysqli_query($conexion, "SELECT * from tabla_estudiantes where  Matrícula = '$matricu'")
    or die ("Error al traer los datos");
    
    while($extraido = mysqli_fetch_array($consulta))

    {
        ?>

        <tr>
        <td><?php echo$extraido['Matrícula'];?></td>
        <td><?php echo$extraido['Nombre'];?></td>
        <td><?php echo$extraido['Apellido paterno'];?></td>
        <td><?php echo$extraido['Apellido materno'];?></td>
        <td><?php echo$extraido['Edad'];?></td>
        <td><?php echo$extraido['Especialidad'];?></td>
        <td><?php echo$extraido['Turno'];?></td>
        <td><?php echo$extraido['Grupo'];?></td>
        <td><?php echo$extraido['Semestre'];?></td>
        </tr>

        <?php
    }

    mysqli_close($conexion);
    echo'</table>';

    ?>

    <html>
    <input type="button" onclick="history.back()" name="volver atrás" value="volver atrás">
    </html>