import json
import random
from pathlib import Path

random.seed(0)

SYSTEM = ("Eres el asistente virtual de Banco Andino. Responde de forma formal y cordial, "
          "usando únicamente el contexto entregado. Si el contexto no contiene la respuesta, indícalo.")
APERTURA = "Estimado cliente, con gusto le informo lo siguiente: "
CIERRE = " ¿Puedo ayudarle con algo más? Cordialmente, Banco Andino."
SIN_INFO = ("Estimado cliente, lamentablemente no cuento con información sobre ese tema en la "
            "documentación disponible. Le sugiero comunicarse con un asesor en una sucursal o en "
            "nuestra línea de atención. Cordialmente, Banco Andino.")

HECHOS = [
    {"ctx": "Límites de retiro en cajero. El límite diario de retiro en cajero automático es de 2.000.000 de pesos para cuentas de ahorro y de 3.000.000 de pesos para cuentas corrientes.",
     "preguntas": ["¿Cuánto puedo retirar al día en un cajero?", "¿Cuál es el límite diario de retiro?",
                   "¿Hasta qué monto puedo sacar en cajero con cuenta de ahorros?", "limite retiro cuenta corriente cajero",
                   "¿Me dejan retirar 3 millones en un cajero?", "¿Cuánta plata puedo sacar por día?"],
     "resp": "El límite diario de retiro en cajero automático es de 2.000.000 de pesos para cuentas de ahorro y de 3.000.000 de pesos para cuentas corrientes."},
    {"ctx": "Transferencias. Las transferencias a otros bancos tienen un costo de 3.500 pesos y se acreditan en un máximo de 30 minutos.",
     "preguntas": ["¿Cuánto cuesta transferir a otro banco?", "¿Cuánto demora una transferencia a otro banco?",
                   "¿Tiene costo enviar plata a una cuenta de otra entidad?", "costo transferencia interbancaria",
                   "¿En cuánto tiempo llega una transferencia a otro banco?", "¿Qué cobran por transferencias a otras entidades?"],
     "resp": "Las transferencias a otros bancos tienen un costo de 3.500 pesos y se acreditan en un máximo de 30 minutos."},
    {"ctx": "Transferencias. Las transferencias entre cuentas propias no tienen costo.",
     "preguntas": ["¿Cuesta mover plata entre mis propias cuentas?", "¿Cobran por transferir entre mis cuentas?",
                   "¿Es gratis pasar dinero de mi ahorro a mi corriente?", "costo transferencia cuentas propias",
                   "¿Tiene algún cobro transferir entre cuentas mías?", "¿Cuánto me cobran por pasar plata entre mis cuentas?"],
     "resp": "Las transferencias entre cuentas propias no tienen costo."},
    {"ctx": "Verificación adicional. Las transferencias superiores a 10.000.000 de pesos en una sola operación requieren verificación por llamada de un asesor antes de ser procesadas.",
     "preguntas": ["¿Qué pasa si transfiero 15 millones?", "¿Hay verificación para transferencias grandes?",
                   "¿Desde qué monto piden llamada de un asesor?", "transferencia mayor a 10 millones requisitos",
                   "¿Por qué me llamaron antes de procesar mi transferencia?", "¿Puedo hacer una transferencia de 12.000.000 sin verificación?"],
     "resp": "Las transferencias superiores a 10.000.000 de pesos en una sola operación requieren verificación por llamada de un asesor antes de ser procesadas."},
    {"ctx": "Atención de reclamos. El plazo máximo para responder un reclamo es de 15 días hábiles. Cuando requiere investigación adicional, el plazo se puede ampliar en 8 días hábiles más, siempre que se notifique al cliente por escrito.",
     "preguntas": ["¿Cuánto tardan en responder un reclamo?", "¿Cuál es el plazo máximo para un reclamo?",
                   "¿Pueden extender el plazo de mi reclamo?", "tiempo respuesta reclamos",
                   "Radiqué un reclamo, ¿en cuántos días me responden?", "¿Cuántos días hábiles tiene el banco para contestar una queja?"],
     "resp": "El plazo máximo para responder un reclamo es de 15 días hábiles. Si requiere investigación adicional, puede ampliarse en 8 días hábiles más, previa notificación escrita al cliente."},
    {"ctx": "Reclamos por fraude. Los reclamos por presunto fraude tienen prioridad y se atienden en un máximo de 5 días hábiles. El cliente recibe un número de radicado al presentar el reclamo.",
     "preguntas": ["¿Cuánto demoran los reclamos por fraude?", "Me hicieron un cargo que no reconozco, ¿en cuánto responden?",
                   "¿Los reclamos por fraude tienen prioridad?", "plazo reclamo fraude",
                   "¿Recibo algún número al reportar un fraude?", "¿Qué tan rápido atienden un presunto fraude?"],
     "resp": "Los reclamos por presunto fraude tienen prioridad y se atienden en un máximo de 5 días hábiles. Al presentar el reclamo, usted recibe un número de radicado."},
    {"ctx": "Bloqueo por pérdida o robo. El cliente debe reportar la pérdida o el robo de su tarjeta a la línea de atención disponible las 24 horas. El bloqueo es inmediato y el cliente recibe un número de confirmación.",
     "preguntas": ["¿Qué hago si perdí mi tarjeta?", "Me robaron la tarjeta, ¿cómo la bloqueo?",
                   "¿La línea para bloquear tarjetas atiende de noche?", "bloqueo tarjeta pérdida",
                   "¿El bloqueo de la tarjeta es inmediato?", "¿Me dan algún comprobante al bloquear mi tarjeta?"],
     "resp": "Debe reportar la pérdida o el robo de su tarjeta a la línea de atención, disponible las 24 horas. El bloqueo es inmediato y usted recibirá un número de confirmación."},
    {"ctx": "Reposición. La primera reposición de tarjeta en el año es gratuita. A partir de la segunda reposición, el costo es de 25.000 pesos.",
     "preguntas": ["¿Cuánto cuesta reponer mi tarjeta?", "¿La reposición de tarjeta es gratis?",
                   "Ya cambié la tarjeta una vez este año, ¿cuánto pago por otra?", "costo reposición tarjeta",
                   "¿Cuántas reposiciones gratuitas tengo al año?", "¿Cobran por una tarjeta nueva si la dañé?"],
     "resp": "La primera reposición de tarjeta en el año es gratuita. A partir de la segunda reposición, el costo es de 25.000 pesos."},
    {"ctx": "Cuota de manejo. La cuota de manejo de la tarjeta de crédito se exonera cuando el cliente realiza al menos 5 compras en el mes.",
     "preguntas": ["¿Cómo evito pagar la cuota de manejo?", "¿Cuántas compras necesito para que no me cobren la cuota de manejo?",
                   "¿Se puede exonerar la cuota de manejo de la tarjeta de crédito?", "cuota de manejo exoneración",
                   "Hice 6 compras este mes, ¿me cobran cuota de manejo?", "¿Qué condición hay para no pagar el manejo de la tarjeta?"],
     "resp": "La cuota de manejo de la tarjeta de crédito se exonera cuando usted realiza al menos 5 compras en el mes."},
]

FUERA_DE_TEMA = [
    "¿Cuál es la tasa de interés del crédito de vivienda?", "¿Cómo abro un CDT?", "¿Quién ganó el partido anoche?",
    "¿Cuál es la capital de Francia?", "¿Qué requisitos hay para un crédito de libranza?", "¿A qué hora abre la sucursal del centro?",
    "¿Cómo cambio la clave de la app?", "¿El banco ofrece seguro de vida?", "Dame una receta de arroz con pollo",
    "¿Cuántos empleados tiene el banco?",
]

def ejemplo(ctx, pregunta, respuesta):
    return {"messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Contexto:\n{ctx}\n\nPregunta: {pregunta}"},
        {"role": "assistant", "content": respuesta},
    ]}

datos = []
for h in HECHOS:
    for q in h["preguntas"]:
        datos.append(ejemplo(h["ctx"], q, APERTURA + h["resp"] + CIERRE))
for q in FUERA_DE_TEMA:
    for h in random.sample(HECHOS, 2):          # contexto irrelevante a propósito
        datos.append(ejemplo(h["ctx"], q, SIN_INFO))

random.shuffle(datos)
val, train = datos[:12], datos[12:]
out = Path("data/finetune")
out.mkdir(parents=True, exist_ok=True)
for nombre, lote in [("train.jsonl", train), ("val.jsonl", val)]:
    with open(out / nombre, "w", encoding="utf-8") as f:
        for ex in lote:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
print(f"train={len(train)} val={len(val)}")