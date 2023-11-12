import sys
import os
import re

from tvm.contrib.mlir.parser import mlir_code_parse
from tvm.contrib.mlir.printer import Printer, Visitor
from tvm.contrib.mlir.artemis_printer import ArtemisPrinter

mlir_files = [file for file in os.listdir() if file.endswith(".mlir")]


kernel_config = ""

def replace_regex(file, pattern, replace):
    with open(file, "r") as f:
        content = f.read()
    content = re.sub(pattern, replace, content)
    with open(file, "w") as f:
        f.write(content)


def compile_all_cuda_files():
    for mlir_file in mlir_files:
        kernel_name = mlir_file.replace(".mlir", "")
        os.system(f'nvcc -O3 -ccbin=g++ -std=c++11 -Xcompiler "-fPIC -fopenmp -O3 -fno-strict-aliasing" --use_fast_math -Xptxas "-dlcm=ca" -c {kernel_name}.cu -o {kernel_name}.o')
    os.system(f'nvcc -O3 -ccbin=g++ -std=c++11 -Xcompiler "-fPIC -fopenmp -O3 -fno-strict-aliasing" --use_fast_math -Xptxas "-dlcm=ca" -c main.cu -o main.o')

    # compile main.cu with all .o files
    # os.system(f'nvcc -ccbin=g++ -std=c++11 -Xcompiler "-fPIC -fopenmp -O3 -fno-strict-aliasing" --use_fast_math -Xptxas "-dlcm=ca" -c main.cu -o main.o')
    os.system(f'nvcc -ccbin=g++ -std=c++11 -Xcompiler "-fPIC -fopenmp -fno-strict-aliasing" --use_fast_math -Xptxas "-dlcm=ca" main.cpp *.o -o main')

def compile():
    for mlir_file in mlir_files:
        stencil_name = mlir_file.replace(".mlir", "")
        print(f"translate {mlir_file} into {stencil_name}.cu")
        with open(mlir_file, "r") as f:
            mlir_code = f.readlines()
        # 1. Parse mlir file using recursive descent, reuse tvm visit_expr infrastructure
        expr = mlir_code_parse(mlir_code)
        # 2. expr is an ir consist of relay ir and self defined arithmetic ir, then partly translate it into artemis ir.
        with open(f"{stencil_name}.ir", "w") as f:
            ArtemisPrinter(f).visit(expr)
        
        # 3. Parse the ir file into an artemis idsl file and generate a config file
        os.system(f"python3 parse_to_singlekernel.py {stencil_name}.ir")
        # replace regex expression kernel_apply_(.*) to kernel_(stencil_name)
        replace_regex(f"{stencil_name}.idsl", r"kernel_apply_(\d+)", f"kernel_{stencil_name}")
        replace_regex(f"{stencil_name}_config.txt", r"kernel_apply_(\d+)", f"kernel_{stencil_name}")
        with open(f"{stencil_name}.idsl", "r") as f:
            content = f.read()
            re.sub(r"kernel_apply_(.*)", f"kernel_{stencil_name}", content)
            
        with open(f"{stencil_name}.idsl", "w") as f:
            f.write(content)
        
        # 4. Parse the origin cuda file, and get def-use chain
        
        # os.system(f"stencilgen {stencil_name}.idsl {kernel_config}")
        # os.system(f"mv out.cu {mlir_file.replace('.mlir', '.cu')}")

    os.system(f"python3 parse_cu_main.py {cu_file}")
    os.system("python3 gen_cuda.py")
    # compile all the cuda files
    compile_all_cuda_files()
    clean()

def clean():
    for mlir_file in mlir_files:
        stencil_name = mlir_file.replace(".mlir", "")
        os.system(f"rm {stencil_name}.ir {stencil_name}.idsl {stencil_name}_config.txt")


def clean_cu_and_object():
    for mlir_file in mlir_files:
        stencil_name = mlir_file.replace(".mlir", "")
        os.system(f"rm {stencil_name}.cu {stencil_name}.o")

def clean_main():
    os.system("rm main.cpp main.o main")
    
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 translate.py [compile|clean]")
        exit(0)
    if sys.argv[1] == "compile":
        cu_file = [file for file in os.listdir() if file.endswith(".cu") and file != "main.cu"]
        assert(len(cu_file) == 1)
        cu_file = cu_file[0]
        compile()
    elif sys.argv[1] == "clean":
        clean()
        clean_cu_and_object()
        clean_main()
    else:
        print("Usage: python3 translate.py [compile|clean]")
        exit(0)