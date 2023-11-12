import os
import re
import sys


dsl_list = [file for file in os.listdir() if file.endswith(".idsl")]

L = M = N = 320

# If you want to change the size of the input, please run the script like this:
# python3 gen_cuda.py 320
if len(sys.argv) > 1:
    L = M = N = int(sys.argv[1])

def copy_to_device(arg):
    template = f'''
    double *{arg};
	cudaMalloc (&{arg}, sizeof(double )*(L - 0)*(M - 0)*(N - 0));
	check_error ("Failed to allocate device memory for {arg}\\n");
    cudaMemcpy ({arg}, h_{arg}, sizeof(double )*(L - 0)*(M - 0)*(N - 0), cudaMemcpyHostToDevice);
'''
    return template

def alloc_in_device(arg):
    template = f'''
    double *{arg};
    cudaMalloc (&{arg}, sizeof(double )*(L - 0)*(M - 0)*(N - 0));
    check_error ("Failed to allocate device memory for {arg}\\n");
'''
    return template

def gen_cuda_main(config_name="config.txt"):
    with open(config_name, "r") as f:
        lines = f.read().split("\n")
    args = lines[0].split(", ")
    mid_vars = lines[1].split(", ")
    out_vars = lines[-1][len("copyout "):-1].split(", ")
    kernels = []
    for line in lines[2:-1]:
        kernels.append(line.split(" ")[0])
    para_list = []
    header = '''
    #include <stdio.h>

    
    
#include "cuda.h"
#define max(x,y)    ((x) > (y) ? (x) : (y))
#define min(x,y)    ((x) < (y) ? (x) : (y))
#define ceil(a,b)   ((a) % (b) == 0 ? (a) / (b) : ((a) / (b)) + 1)
'''
    check_error = '''
    void check_error (const char* message) {
	cudaError_t error = cudaGetLastError ();
	if (error != cudaSuccess) {
		printf ("CUDA error : %s, %s\\n", message, cudaGetErrorString (error));
		exit(-1);
	}
}'''
    for index, kernel in enumerate(lines[2:-1]):
        kernel_name = kernel.split(" ")[0]
        start_index = kernel.find("(")
        end_index = kernel.find(")")
        paras = kernel[start_index + 1: end_index].split(", ")
        para_list.append(paras)
    to_print = [header, check_error]
    for kernel_name, paras in zip(kernels, para_list):
        # paras.extend(["L", "M", "N"])
        lmn = ["int L", "int M", "int N"]
        to_print.append(f'__global__ void {kernel_name} ({", ".join(list(map(lambda x: "double * __restrict__ " + x, paras)))}, {", ".join(lmn)});')
    
    kernel_def = f'extern "C" void host_code ({", ".join(list(map(lambda x: "double *h_" + x, args + out_vars)))}, int L, int M, int N) {{'
    to_print.append(kernel_def)
    for arg in args:
        to_print.append(copy_to_device(arg))
    for arg in mid_vars:
        to_print.append(alloc_in_device(arg))
        
    
    for index, kernel in enumerate(kernels):
        config = kernel2blockconfig[kernel[len("kernel_"):]]
        block_config = f"dim3 blockconfig_{index} ({config['bx']}, {config['by']}, {config['bz']});"
        to_print.append(block_config)
        grid_config = kernel2grid[kernel[len("kernel_"):]].replace("gridconfig_1", f"gridconfig_{index}").replace("blockconfig_1", f"blockconfig_{index}")
        to_print.append(grid_config)

    for index, (kernel, paras) in enumerate(zip(kernels, para_list)):
        paras.extend(["L", "M", "N"])
        to_print.append(f'{kernel} <<<gridconfig_{index}, blockconfig_{index}>>> ({", ".join(paras)});')
        
    for arg in out_vars:
        to_print.append(f'cudaMemcpy (h_{arg}, {arg}, sizeof(double )*(L - 0)*(M - 0)*(N - 0), cudaMemcpyDeviceToHost);')
        
    to_print.append("}")
    with open("main.cu", "w") as f:
        f.write("\n".join(to_print))
    to_print.clear()

    header_main= '''
#include <cstdio>
#include <cassert>
#include "common/common.hpp"
'''
    to_print.append(header_main)
    
    # gen "extern C" host_code
    extern_c = f'extern "C" void host_code ({", ".join(list(map(lambda x: "double * ", args + out_vars)))}, int L, int M, int N);'
    to_print.append(extern_c)
    
    # here to print the main function
    to_print.append("\n")
    to_print.append("int main (int argc, char **argv) {")
    to_print.append("    const int N = 320;")

    for arg in args + out_vars:
        array_init = f'	double (*h_{arg})[N][N] = (double (*)[N][N]) getRandom3DArray<double>(N, N, N);'
        to_print.append(array_init)
        
    # call host_code
    to_print.append(f'    host_code ({", ".join(list(map(lambda x: f"(double *) h_{x}", args + out_vars)))}, N, N, N);')
        
    for arg in args + out_vars:
        #delete array
        array_delete = f'	delete[] (h_{arg});'
        to_print.append(array_delete)

    to_print.append("    return 0;")
    # end of main
    to_print.append("}")
    with open("main.cpp", "w") as f:
        f.write("\n".join(to_print))


def compile_dsl(dsl_name):
    kernel_name = dsl_name[:-5]
    block_config = {}
    os.system(f"stencilgen {dsl_name} --ndim L=320,M=320,N=320")
    with open("out.cu", "r") as f:
        content = f.read()
    content = content.replace("void check_error", "inline void check_error")
    lines = content.split("\n")
    for index, line in enumerate(lines):
        if line.startswith('extern "C"'):
            end_index = index
        else:
            if "dim3 gridconfig" in line:
                grid_dim = line   
            else:
                line = line.strip()
                pattern = r"#define\s+(\w+)\s+(\d+)"
                match = re.search(pattern, line)
                if not match:
                    continue
                define_name = match.group(1)
                define_value = match.group(2)
                block_config[define_name] = define_value
                # use regex to match "#define bx 16"
                
    with open(f"{kernel_name}.cu", "w") as f:
        f.write("\n".join(lines[:end_index]))
    # os.system(f'nvcc -O3 -ccbin=g++ -std=c++11 -Xcompiler "-fPIC -fopenmp -O3 -fno-strict-aliasing" --use_fast_math -Xptxas "-dlcm=ca" -c {kernel_name}.cu -o {kernel_name}.o')
    return grid_dim, block_config
    # os.system(f"mv out.cu {kernel_name}.cu")




kernel2grid = {}
kernel2blockconfig = {}

# First, compile all the dsls and generate the corresponding kernel files. out.cu => dslname.cu
for dsl in dsl_list:
    grid_dim, block_config = compile_dsl(dsl)
    kernel2grid[dsl[:-5]] = grid_dim
    kernel2blockconfig[dsl[:-5]] = block_config
    
gen_cuda_main()
# gen_main()