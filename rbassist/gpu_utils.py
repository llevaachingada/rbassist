import torch
import os

def select_optimal_device(prefer_gpu=True):
    """
    Select the optimal device for processing.
    
    Args:
        prefer_gpu (bool): Whether to prefer GPU if available. Defaults to True.
    
    Returns:
        torch.device: Selected device for processing
    """
    if prefer_gpu and torch.cuda.is_available():
        # Intelligent GPU selection
        gpu_count = torch.cuda.device_count()
        if gpu_count > 1:
            # Multiple GPUs: Find the one with most free memory
            free_memories = [torch.cuda.mem_get_info(i)[0] for i in range(gpu_count)]
            best_gpu = free_memories.index(max(free_memories))
            device = torch.device(f'cuda:{best_gpu}')
        else:
            device = torch.device('cuda:0')
        
        print(f"Using GPU: {torch.cuda.get_device_name(device)}")
        return device
    
    return torch.device('cpu')

def get_system_info():
    """
    Comprehensive system processing capabilities report.
    
    Returns:
        dict: Detailed system processing information
    """
    return {
        'cpu': {
            'total_cores': os.cpu_count(),
            'available_cores': len(os.sched_getaffinity(0))
        },
        'gpu': {
            'cuda_available': torch.cuda.is_available(),
            'device_count': torch.cuda.device_count(),
            'devices': [
                {
                    'name': torch.cuda.get_device_name(i),
                    'total_memory': torch.cuda.get_device_properties(i).total_memory,
                    'free_memory': torch.cuda.mem_get_info(i)[0]
                } for i in range(torch.cuda.device_count())
            ] if torch.cuda.is_available() else []
        }
    }

def optimize_processing_resources(operation_type='embedding'):
    """
    Dynamically optimize processing resources based on operation type.
    
    Args:
        operation_type (str): Type of operation ('embedding', 'analysis', 'indexing')
    
    Returns:
        dict: Optimized processing configuration
    """
    system_info = get_system_info()
    device = select_optimal_device()
    
    config = {
        'device': device,
        'workers': max(1, os.cpu_count() - 2),  # Leave 2 cores free
        'batch_size': 32  # Default batch size
    }
    
    if device.type == 'cuda':
        gpu_memory = system_info['gpu']['devices'][0]['free_memory'] if system_info['gpu']['devices'] else 0
        
        # Dynamically adjust based on operation and available resources
        if operation_type == 'embedding':
            config['batch_size'] = min(64, int(gpu_memory / (1024 * 1024 * 100)))  # Adjust batch size based on GPU memory
            config['workers'] = min(8, os.cpu_count())
        elif operation_type == 'analysis':
            config['batch_size'] = 16
            config['workers'] = max(4, os.cpu_count() // 2)
        elif operation_type == 'indexing':
            config['batch_size'] = 128
            config['workers'] = os.cpu_count()
    
    return config
