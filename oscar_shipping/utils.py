def del_key(dict, key):
    """Delete a pair key-value from dict given 
    """
    for k in list(dict.keys()):
        if k == key:
            del dict[k]