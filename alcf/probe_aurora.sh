#!/bin/bash
D=/lus/flare/projects/DD_plasma_physics/sarthaksharma_hasb
O=$D/probe_aurora.txt
{
echo "HOST $(hostname)"; date
ls /flare/datasets/model-weights/hub | grep -i -E "qwen|llama|mistral|gpt-oss|phi|granite|gemma|hermes|olmo|smol|glm"
module load frameworks
python -c "import vllm,torch;print('vllm',vllm.__version__,'torch',torch.__version__)" 2>&1 | tail -1
python -c "import openai;print('openai',openai.__version__)" 2>&1 | tail -1
python -c "from vllm.entrypoints.openai.tool_parsers import ToolParserManager as T;print(sorted(T.tool_parsers.keys()))" 2>&1 | tail -1
python -c "from vllm.tool_parsers import ToolParserManager as T;print(sorted(T.tool_parsers.keys()))" 2>&1 | tail -1
xpu-smi discovery 2>&1 | grep -c "Device Name"
which python; python --version
} > $O 2>&1
