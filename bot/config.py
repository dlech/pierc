
def config(filename):
    """ Process a file (located at filename)
        containing a series of key-value pairs
        this: awesome
        numkids: 10
        funk: soulbrother
        Into a dictionary. (dict[this] = "awesome")
    """
    try:
        config_data = dict()
        db_file = open(filename, "r")
        for line in db_file:
            if line.startswith("#"):
                continue
            idx = line.index(":")
            key = line[0:idx]
            value = line[idx+1:len(line)].strip()
            config_data[key] = value
        db_file.close()
        return config_data
    except ValueError:
        print "bad line in ", filename
    except:
        print filename, "missing."
        exit()

if __name__ == "__main__":
    irc_config = config("mysql_config.txt")
    for key, value in irc_config.iteritems():
        print key, value
    irc_config = config("irc_config.txt")
    for key, value in irc_config.iteritems():
        print key, value
    webdav_config = config("webdav_config.txt")
    for key, value in webdav_config.iteritems():
        print key, value
