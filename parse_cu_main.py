import sys
import os
import re

# parse cu file to get the def-use chain

# first, get all input and output variables
# variables like "arg(\d+)" are input variables
# variables like "func_(\d+)" are intermediate variables
# in cu file, first find struct parameter, then find all variables in it
'''
struct parameter
{
  Storage3D arg0;
  Storage3D arg1;
  Storage3D arg2;
  Storage3D arg3;
  Storage3D arg4;
  Storage3D arg5;
  Storage3D arg6;
  Storage3D arg7;
  Storage3D arg8;
  Storage3D arg9;
  Storage3D arg10;
  Storage3D arg11;
  Storage3D arg12;
  Storage3D func_29;
  Storage3D func_31;
  Storage3D func_fuse_0_1;
  Storage3D func_23;
  Storage3D func_fuse_0_0;
  Storage3D func_28;
  Storage3D func_30;
  Storage3D func_27;
  Storage3D func_24;
};
'''

def get_all_variables(cu_file):
    with open(cu_file, "r") as f:
        content = f.read()
    pattern = "struct parameter\n\{\n((  Storage3D arg\d+;\n)+)((  Storage3D func_(.+)+;\n)+)\};"

    match = re.search(pattern, content)
    input_variables = match.group(1)
    intermediate_variables = match.group(3)
    input_variables = re.findall(r"  Storage3D (arg\d+);", input_variables)
    intermediate_variables = re.findall(r"  Storage3D (func_\w+);", intermediate_variables)
    return input_variables, intermediate_variables

# Then parse the kernel functions, store stencil_23, stencil_24... in a list
'''
extern "C" {
  void _mlir_ciface_kernel_stencil_23(Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *);
void _mlir_ciface_kernel_stencil_24(Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *);
void _mlir_ciface_kernel_fuse_25_26(Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *);
void _mlir_ciface_kernel_stencil_27(Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *);
void _mlir_ciface_kernel_stencil_29(Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *);
void _mlir_ciface_kernel_stencil_31(Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *);
void _mlir_ciface_kernel_stencil_28(Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *);
void _mlir_ciface_kernel_stencil_30(Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *, Storage3D *);
}
'''

def get_all_kernels(cu_file):
    with open(cu_file, "r") as f:
        content = f.read()
    pattern = r"extern \"C\" \{\n  ((void _mlir_ciface_kernel_(.+)\n(.*))+)\}"
    match = re.search(pattern, content)
    kernels = match.group(1)
    kernels = re.findall(r"void _mlir_ciface_kernel_(\w+)", kernels)
    return kernels

def parse_kernel_call_in_a_stream(stream_call_list):
    call_list = []
    for call in stream_call_list:
        if "_mlir_ciface_kernel_" in call:
            kernel_name = re.search(r"_mlir_ciface_kernel_(\w+)", call).group(1)
            args_str = re.search(r"\((.+)\)", call).group(1)
            kernel_args = [x[1:] for x in args_str.split(", ")]
            call_list.append((kernel_name, kernel_args))
        elif call.strip().startswith("sync"):
            sync = call.strip().split("+=")[0]
            call_list.append((sync, []))    
    return call_list
            

def parse_launch_kernel(cu_file):
    with open(cu_file, "r") as f:
        content = f.read()
    pattern = r"void \*launch_kernel.+\n\{\n((.*\n)+?)    return NULL;\n\}"
    matches = re.findall(pattern, content)
    stream_list = []
    for match in matches:
        match = match[0]
        stream_list.append(parse_kernel_call_in_a_stream(match.split("\n")))
    return stream_list


def parse_single_kernel_config(kernel_name, mlir_args):
    with open(f"{kernel_name}_config.txt", "r") as f:
        content = f.read()
    # The format of content is like this:
    """
    arg0, arg1, arg2, arg3, arg4, arg5, arg6, arg7, arg8, arg9, arg10, arg11, arg12, arg13, arg14, arg15
    apply_27_0, apply_27_1
    kernel_fuse_25_26 (apply_27_0, apply_27_1, arg5, arg13, arg6) ;
    copyout apply_27_0, apply_27_1;
    """
    content = content.split("\n")
    input_variables = content[0].split(", ")
    assert len(mlir_args) == len(input_variables)
    origin_input = [x for x in mlir_args if x.startswith("arg")]
    len_origin_input = len(origin_input)
    intermediate_variables = content[1].split(", ")
    idsl_kernel_args = content[2][len(f"kernel_{kernel_name} ("):-3].split(", ")
    out_variables = content[3][len("copyout "):].split(", ")
    len_output = len(out_variables)
    # get the last "len_output" of mlir_args
    mlir_output_args = mlir_args[-len_output:]
    new_arg_list = []
    for i in range(len_output):
        new_arg_list.append(mlir_output_args[i])
    for i in range(len_output, len(idsl_kernel_args)):
        # find the index of idsl_kernel_args[i] in input_variables
        index = input_variables.index(idsl_kernel_args[i])
        new_arg_list.append(mlir_args[index])
    return new_arg_list
        
    
def gen_config_file(input_variables, intermediate_variables, kernels, stream_list):
    to_print = []
    to_print.append(", ".join(input_variables))
    to_print.append(", ".join(intermediate_variables))
    for kernel_call_list in stream_list:
        for kernel_call in kernel_call_list:
            if kernel_call[0] in kernels:
                new_arg_list = parse_single_kernel_config(kernel_call[0], kernel_call[1])
                to_print.append(f"kernel_{kernel_call[0]} ({', '.join(new_arg_list)}) ;")
    out_var = []
    to_print.append("copyout " + ", ".join(out_var))
    # print to file "config.txt"
    with open("config.txt", "w") as f:
        f.write("\n".join(to_print))
    
    
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 parse_cu.py [cu_file]")
        exit(0)
    cu_file = sys.argv[1]
    input_variables, intermediate_variables = get_all_variables(cu_file)
    print(input_variables)
    print(intermediate_variables)
    kernels = get_all_kernels(cu_file)
    print(kernels)
    stream_list = parse_launch_kernel(cu_file)
    gen_config_file(input_variables, intermediate_variables, kernels, stream_list)
    
    