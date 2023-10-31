
with open("test.ir", "r") as f:
    lines = f.readlines()

symbol_table = {}

parse_stencil_lines = False
apply_kernels = []

store_result_list = []
input_args = None

mid_vars = []
para2input = {}

for line in lines:
    if not line:
        continue
    if parse_stencil_lines:
        if line.strip()[0] == "}":
            stencil_lines.append(line)
            apply_kernels.append(stencil_lines)
            parse_stencil_lines = False
        else:
            stencil_lines.append(line)
        continue
    line = line.strip()
    line_split = line.split()
    if "stencil.load" in line:
        symbol_table[line_split[0]] = line_split[3]
    elif line.startswith("stencil"):
        start_index = line.find("(")
        end_index = line.find(")") 
        mid_vars.append(line[start_index + 1: end_index].split(", ")[0])
        stencil_lines = [line]
        parse_stencil_lines = True
    elif line.startswith("store"):
        store_result_list.append(line.split()[1])
    elif line.startswith("var_"):
        symbol_table[line.split()[0]] = line.split()[2]
    elif line.startswith("@"):
        start_index = line.find("(")
        end_index = line.find(")")
        input_args = line[start_index + 1: end_index].split(", ")

assert store_result_list
assert input_args is not None

config = []

arg_list = ", ".join(input_args + mid_vars)
config.append(", ".join(input_args))
config.append(", ".join(mid_vars))

header = """
parameter L,M,N;
iterator k, j, i;
"""

declare_statement = "double " + ", ".join(list(map(lambda x: x + "[L,M,N]", (input_args + mid_vars))))  + ";"
copy_statement = "copyin " + ", ".join(input_args) + ";"

# print(header)
# print(declare_statement)
# print(copy_statement)

def gen_header():
    return [header]

apply_first_line_list = []

def gen_declare(arg_list):
    declare_line = "double " + ", ".join([f"{arg}[L,M,N]" for arg in arg_list]) + ";"
    copy_line = "copyin " + ", ".join(arg_list[1:]) + ";"
    return [declare_line, copy_line]

# here to print all apply kernels
# First, print parameter and iterator header
# Second, print all paras, include input and output, the output is the first para
# print all if them to different files.

for apply_kernel in apply_kernels:
    to_print = gen_header() # An artemis application is started with the same header
    first_line = apply_kernel[0]
    start_index = first_line.find("(")
    end_index = first_line.find(")") 
    paras = first_line[start_index + 1: end_index]
    para_list = paras.split(", ")
    new_para_list = []
    for para in para_list:
        next_symbol = symbol_table.get(para, para)
        while next_symbol:
            now_symbol = next_symbol
            next_symbol = symbol_table.get(next_symbol)
        new_para_list.append(now_symbol)
        para2input[para] = now_symbol
    to_print.extend(gen_declare(new_para_list))
    first_line = first_line.replace(paras, ", ".join(new_para_list))
    apply_first_line_list.append(first_line)
    to_print.append(first_line)
    # print(first_line)

    for line in apply_kernel[1:]:
        for k, v in para2input.items():
            line = line.replace(k, v)
        to_print.append(line)
    call_statement = first_line[len("stencil "):-1]
    call_statement = call_statement + ";"
    copy_out_statement = "copyout " + ", ".join([new_para_list[0]]) + ";"
    to_print.append(call_statement)
    to_print.append(copy_out_statement)
    with open(f"{new_para_list[0]}.idsl", "w") as f:
        f.write("\n".join(to_print))

for apply_kernel in apply_first_line_list:
    call_statement = apply_kernel[len("stencil "):-1]
    call_statement = call_statement + ";"
    config.append(call_statement)
    print(call_statement)
    
copy_out_statement = "copyout " + ", ".join(store_result_list) + ";"
config.append(copy_out_statement)
print(copy_out_statement)

with open("config.txt", "w") as f:
    f.write("\n".join(config))