"""Small CLI adapter around the official GeoChat repository.
Run from the SatQuery environment after setup_models.py --geochat."""
import argparse, json, sys
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--repo',required=True); ap.add_argument('--model',required=True); ap.add_argument('--image',required=True); ap.add_argument('--prompt',required=True); ap.add_argument('--mode',default='caption'); ap.add_argument('--max-new-tokens',type=int,default=256)
    a=ap.parse_args(); sys.path.insert(0,a.repo)
    import torch
    from PIL import Image
    from geochat.constants import IMAGE_TOKEN_INDEX, DEFAULT_IMAGE_TOKEN, DEFAULT_IM_START_TOKEN, DEFAULT_IM_END_TOKEN
    from geochat.conversation import conv_templates
    from geochat.model.builder import load_pretrained_model
    from geochat.mm_utils import tokenizer_image_token, process_images, get_model_name_from_path
    model_name=get_model_name_from_path(a.model)
    tokenizer,model,image_processor,context_len=load_pretrained_model(a.model,None,model_name,False,False)
    image=Image.open(a.image).convert('RGB')
    prompt=a.prompt
    if a.mode=='grounding': prompt='[grounding]\n'+prompt
    prompt=DEFAULT_IMAGE_TOKEN+'\n'+prompt
    if getattr(model.config,'mm_use_im_start_end',False): prompt=DEFAULT_IM_START_TOKEN+DEFAULT_IMAGE_TOKEN+DEFAULT_IM_END_TOKEN+'\n'+a.prompt
    conv=conv_templates['vicuna_v1'].copy(); conv.append_message(conv.roles[0],prompt); conv.append_message(conv.roles[1],None); full=conv.get_prompt()
    image_tensor=process_images([image],image_processor,model.config)[0]
    ids=tokenizer_image_token(full,tokenizer,IMAGE_TOKEN_INDEX,return_tensors='pt').unsqueeze(0)
    device='cuda' if torch.cuda.is_available() else 'cpu'; ids=ids.to(device); image_tensor=image_tensor.to(device=device,dtype=torch.float16 if device=='cuda' else torch.float32)
    with torch.inference_mode():
        out=model.generate(ids,images=image_tensor.unsqueeze(0),image_sizes=[image.size],do_sample=False,max_new_tokens=a.max_new_tokens,use_cache=True)
    text=tokenizer.batch_decode(out,skip_special_tokens=True)[0].strip()
    print(json.dumps({'text':text,'mode':a.mode,'model':'GeoChat-7B'}))
if __name__=='__main__': main()
