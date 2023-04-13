def get_file_extension(data):
    ## webp
    if data[8:12] == b"WEBP":
        return ".webp", "image/webp"

    ## png
    elif data[0:4] == b"\x89PNG":
        return ".png", "image/png"

    ## gif
    elif data[0:4] == b"GIF8":
        return ".gif", "image/gif"

    ## jpg
    elif data[0:3] == b"\xFF\xD8\xFF":
        return ".jpg", "image/jpeg"

    ## else
    else:
        return None
