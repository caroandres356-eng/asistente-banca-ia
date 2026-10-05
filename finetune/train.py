import argparse
from datasets import load_dataset
from transformers import (AutoTokenizer, AutoModelForCausalLM, TrainingArguments,
                          Trainer, DataCollatorForSeq2Seq)
from peft import LoraConfig, get_peft_model

parser = argparse.ArgumentParser()
parser.add_argument("--r", type=int, default=16)
parser.add_argument("--epochs", type=int, default=3)
cli = parser.parse_args()

BASE = "Qwen/Qwen2.5-0.5B-Instruct"
tok = AutoTokenizer.from_pretrained(BASE)

def codificar(ex):
    msgs = ex["messages"]
    prompt = tok.apply_chat_template(msgs[:-1], tokenize=False, add_generation_prompt=True)
    completo = prompt + msgs[-1]["content"] + tok.eos_token
    p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
    f_ids = tok(completo, add_special_tokens=False)["input_ids"][:512]
    # Solo la respuesta cuenta para la pérdida: el prompt se enmascara con -100
    labels = ([-100] * len(p_ids) + f_ids[len(p_ids):])[:512]
    return {"input_ids": f_ids, "attention_mask": [1] * len(f_ids), "labels": labels}

ds = load_dataset("json", data_files={"train": "data/finetune/train.jsonl",
                                      "val": "data/finetune/val.jsonl"})
ds = ds.map(codificar, remove_columns=["messages"])

modelo = AutoModelForCausalLM.from_pretrained(BASE)
config = LoraConfig(r=cli.r, lora_alpha=2 * cli.r, lora_dropout=0.05,
                    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
                    task_type="CAUSAL_LM")
modelo = get_peft_model(modelo, config)
modelo.print_trainable_parameters()

args = TrainingArguments(
    output_dir="finetune/salida", num_train_epochs=cli.epochs,
    per_device_train_batch_size=2, gradient_accumulation_steps=2,
    learning_rate=2e-4, logging_steps=5, eval_strategy="epoch",
    save_strategy="no", report_to="none")
trainer = Trainer(model=modelo, args=args, train_dataset=ds["train"], eval_dataset=ds["val"],
                  data_collator=DataCollatorForSeq2Seq(tok, padding=True, label_pad_token_id=-100))
trainer.train()
modelo.save_pretrained("finetune/adaptador")
tok.save_pretrained("finetune/adaptador")
print("Adaptador guardado en finetune/adaptador")