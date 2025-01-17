import sys
from subprocess import Popen, PIPE
from Bio import SeqIO
from prometheus_client import start_http_server, Gauge
import time

# Create gauge metrics
progress_percent_metric = Gauge('ML_prediction_progress_percentage', 'Progress of ML predictions (%)')
progress_count_metric = Gauge('ML_prediction_progress_count', 'Progress of ML predictions (count)')
task_completed = Gauge('ML_task_completed', 'Indicates if the ML task is completed')

"""
usage: python pipeline_script.py INPUT.fasta  
approx 5min per analysis
"""

def run_parser(hhr_file):
    """
    Run the results_parser.py over the hhr file to produce the output summary
    """
    cmd = ['python', './results_parser.py', hhr_file]
    print(f'STEP 4: RUNNING PARSER: {" ".join(cmd)}')
    p = Popen(cmd, stdin=PIPE,stdout=PIPE, stderr=PIPE)
    out, err = p.communicate()
    print(out.decode("utf-8"))

def run_hhsearch(a3m_file, machine_id):
    """
    Run HHSearch to produce the hhr file
    """
    
    # If machine_id = 1, meaning the client machine, operate on 3 CPUs, else 1 CPU
    if machine_id == '1':
        num_thread = '3'
    else:
        num_thread = '1'
        
    cmd = ['/home/ec2-user/data/hh_suite/bin/hhsearch',
           '-i', a3m_file, '-cpu', num_thread, '-d', 
           '/home/ec2-user/data/pdb70/pdb70']
    print(f'STEP 3: RUNNING HHSEARCH: {" ".join(cmd)}')
    p = Popen(cmd, stdin=PIPE,stdout=PIPE, stderr=PIPE)
    out, err = p.communicate()
    

def read_horiz(tmp_file, horiz_file, a3m_file):
    """
    Parse horiz file and concatenate the information to a new tmp a3m file
    """
    pred = ''
    conf = ''
    print("STEP 2: REWRITING INPUT FILE TO A3M")
    with open(horiz_file) as fh_in:
        for line in fh_in:
            if line.startswith('Conf: '):
                conf += line[6:].rstrip()
            if line.startswith('Pred: '):
                pred += line[6:].rstrip()
    with open(tmp_file) as fh_in:
        contents = fh_in.read()
    with open(a3m_file, "w") as fh_out:
        fh_out.write(f">ss_pred\n{pred}\n>ss_conf\n{conf}\n")
        fh_out.write(contents)

def run_s4pred(input_file, out_file, machine_id):
    """
    Runs the s4pred secondary structure predictor to produce the horiz file
    """
    
    # If machine_id = 1, meaning the client machine, operate on 3 CPUs, else 1 CPU
    if machine_id == '1':
        num_thread = '3'
    else:
        num_thread = '1'
    print(f'num_thread = {num_thread} for this prediction.')
    
    cmd = ['/usr/bin/python3', '/home/ec2-user/data/s4pred/run_model.py',
           '-t', 'horiz', '-T', num_thread, input_file]
    print(f'STEP 1: RUNNING S4PRED: {" ".join(cmd)}')
    p = Popen(cmd, stdin=PIPE,stdout=PIPE, stderr=PIPE)
    out, err = p.communicate()
    with open(out_file, "w") as fh_out:
        fh_out.write(out.decode("utf-8"))

    
def read_input(file):
    """
    Function reads a fasta formatted file of protein sequences
    """
    print("READING FASTA FILES")
    sequences = {}
    ids = []
    for record in SeqIO.parse(file, "fasta"):
        sequences[record.id] = record.seq
        ids.append(record.id)
    return(sequences)

if __name__ == "__main__":
    
    machine_id = str(sys.argv[1]) # Receive machine ID as the 1st argument
    test = sys.argv[2] # If test == T means testing mode, else non-testing mode
    
    # Open the port to send metrics data
    start_http_server(4505)
    
    if test == 'T':
        sequences = read_input(f'test.fa')
    else:
        sequences = read_input(f'fasta_part_{machine_id}.fasta')
    
    tmp_file = "tmp.fas"
    horiz_file = "tmp.horiz"
    a3m_file = "tmp.a3m"
    hhr_file = "tmp.hhr"
    
    counter = 0
    task_completed.set(0)
    
    # Iterating each items to predict
    for k, v in sequences.items():
        with open(tmp_file, "w") as fh_out:
            fh_out.write(f">{k}\n")
            fh_out.write(f"{v}\n")
        
        run_s4pred(tmp_file, horiz_file, machine_id)
        read_horiz(tmp_file, horiz_file, a3m_file)
        run_hhsearch(a3m_file, machine_id)
        run_parser(hhr_file)
        counter += 1
        progress_percent_metric.set(counter / len(sequences) * 100)
        progress_count_metric.set(counter)
    
    progress_percent_metric.set(100)
    progress_count_metric.set(len(sequences))
    task_completed.set(1)
    # After the code is completed, delay 30s for the metric to be scraped by Prometheus
    time.sleep(30)
    
