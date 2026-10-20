Monami:   
agregar visión del cliente, llenando una encuesta como la de monami, pero enfocado a esta solución. 

El cliente el hace la orden, ya se registra, se acepta, confirmación de que todo funciona y está bien (para que el pedido se pueda mandar)

Trabajador: se cargó la fecha el dia que va a salir (sale tal día), pedidos listos para salir, y pedidos ya entregados, ya está listo el pedido, se le asigna a algun camion en tiempo real, se pulse los camiones disponibles y se muestra la ruta que va a recorrer el camino (tanto para el conductor como para la empresa). El conductor va a tener mapa del producto,  listado de paquetes que lleva, y puntos en el mapa donde se entregan los productos y la ruta establecida. Que haya un rubro en donde aparezca el pedido y menciona pedido por tercero (para ver a qué empresa de paqueteria se utiliza y que tenemos que hacer para contactar) 

**CLIENTE**

Paso 1: Crear el formulario para realizar una orden

Hacer un formulario sencillo, parecido al flujo de MONAMI, enfocado en solicitar el pedido y su entrega.

* Datos del cliente y contacto.  
* Producto solicitado y cantidad.  
* Dirección de entrega, con opción de marcarla en el mapa.  
* Referencias o instrucciones para recibir el pedido.  
* Resumen para revisar la información antes de enviarla.

Paso 2: Mostrar la aceptación y confirmación del pedido

* Mostrar inicialmente el pedido como “Pendiente de confirmación”.  
* Cuando la empresa revise que puede atenderlo, actualizarlo a “Confirmado”.  
* Mostrar al cliente la fecha programada de salida y la fecha estimada de entrega cuando estén disponibles.  
* Si existe algún problema con la información, indicar qué debe corregir.

Paso 3: Crear el seguimiento del pedido

Mostrar un tracker sencillo con estas etapas:()Recibido, Confirmado, Preparando pedido, Listo para salir, En camino  Entregado.)

* Resaltar la etapa actual.  
* Mostrar la fecha estimada de entrega.  
* Indicar si lo entregará la distribuidora o una empresa de paquetería aliada.  
* Cuando salga, permitir consultar el recorrido y el avance de su entrega, mostrando únicamente la información de su pedido.

**EMPRESA**

Paso 4: Crear el panel para revisar y preparar pedidos

* Mostrar las órdenes recibidas y permitir abrir su detalle.  
* Permitir confirmar el pedido o solicitar una corrección.  
* Registrar la fecha programada de salida.  
* Cambiar el estado según avance su preparación.  
* Organizar el panel en pedidos por confirmar, en preparación, listos para salir, en camino y entregados.

Paso 5: Asignar los pedidos a los camiones disponibles

* Mostrar los pedidos listos para salir.  
* Mostrar los camiones disponibles y su capacidad.  
* Al seleccionar un camión, mostrar sus pedidos asignados y su recorrido.  
* Proponer la agrupación de pedidos según cercanía y capacidad del camión.  
* Permitir al trabajador confirmar o ajustar la asignación.  
* Actualizar la disponibilidad de los camiones conforme se utilicen.

Paso 6: Mostrar las rutas para la empresa y el conductor

La empresa podrá seleccionar un camión y consultar:

* Pedidos y paquetes que transporta.  
* Puntos de entrega en el mapa.  
* Orden de las paradas y ruta establecida.  
* Avance de las entregas.

El conductor tendrá una vista sencilla desde su teléfono con:

* Listado de pedidos y paquetes que lleva.  
* Productos y cantidades de cada pedido.  
* Direcciones y contactos de entrega.  
* Mapa con las paradas y el recorrido.  
* Botones para marcar “Entregado” o “Con problema”.

Paso 7: Agregar el apartado “Entrega por tercero”

* Identificar los pedidos que la flota propia no puede cubrir.  
* Permitir asignarlos a una empresa de paquetería aliada.  
* Mostrar el nombre del aliado, su contacto y un botón para contactarlo o solicitar el servicio.  
* Registrar si el servicio está pendiente de aceptación o confirmado.  
* Mantener el pedido dentro del seguimiento general, identificado como “Entrega por tercero”.

Paso 8: Mostrar cómo se ajusta una ruta ante un incidente

* Permitir simular un bloqueo o accidente en un recorrido.  
* Mostrar una alerta en el panel de la empresa.  
* Proponer y visualizar una ruta alternativa.  
* Reflejar el cambio en la vista del conductor y actualizar la estimación del cliente afectado.

Paso 9: Confirmar la entrega y cerrar el pedido

* Permitir al conductor registrar que el pedido fue entregado.  
* Actualizar el pedido en el panel de la empresa.  
* Mostrar al cliente la confirmación y fecha de entrega.  
* Si hubo un inconveniente, mostrar el motivo y permitir que la empresa reprograme la entrega.

Recorrido para presentar la demo

1. El cliente realiza una orden y recibe su código.  
2. La empresa la confirma, programa su salida y la marca como lista.  
3. El trabajador selecciona un camión y revisa la ruta propuesta.  
4. El conductor consulta sus paquetes y puntos de entrega.  
5. Se simula un bloqueo y se muestra el cambio de recorrido.  
6. Otro pedido se asigna a una empresa de paquetería aliada.  
7. Se completa una entrega y el cliente ve actualizado su seguimiento.

Primer diferenciador: convertir los pedidos recibidos en un plan de entregas.

Segundo diferenciador: mostrar que la planificación puede adaptarse durante la operación.

Tercer diferenciador: combinar la flota propia con transporte externo desde una misma plataforma.