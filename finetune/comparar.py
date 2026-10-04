import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

BASE = "Qwen/Qwen2.5-0.5B-Instruct"
SYSTEM = ("Eres el asistente virtual de Banco Andino. Responde de forma formal y cordial, "
          "usando únicamente el contexto entregado. Si el contexto no contiene la respuesta, indícalo.")
tok = AutoTokenizer.from_pretrained(BASE)
base = AutoModelForCausalLM.from_pretrained(BASE)

# Casos NO vistos en el entrenamiento
CASOS = [
    ("Atención telefónica. La línea de atención al cliente funciona de lunes a viernes de 8 a.m. a 6 p.m.",
     "¿Hasta qué hora puedo llamar a la línea de atención?"),
    ("Cuota de manejo. La cuota de manejo de la tarjeta de crédito se exonera cuando el cliente realiza al menos 5 compras en el mes.",
     "¿Cuál es la tasa de interés de los créditos de consumo?"),
]

def responder(modelo, ctx, pregunta):
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Contexto:\n{ctx}\n\nPregunta: {pregunta}"}]
    texto = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    entrada = tok(texto, return_tensors="pt")
    with torch.no_grad():
        salida = modelo.generate(**entrada, max_new_tokens=120, do_sample=False)
    return tok.decode(salida[0][entrada["input_ids"].shape[1]:], skip_special_tokens=True)

print("=== MODELO BASE ===")
for ctx, q in CASOS:
    print(f"\nP: {q}\nR: {responder(base, ctx, q)}")

adaptado = PeftModel.from_pretrained(base, "finetune/adaptador")
print("\n\n=== MODELO + LoRA ===")
for ctx, q in CASOS:
    print(f"\nP: {q}\nR: {responder(adaptado, ctx, q)}")