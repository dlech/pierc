#! /usr/bin/env python
#

#libs
import irclib
import sys
import re
import time
import datetime
import easywebdav
import subprocess

#mine
import pierc_db
import config


# Configuration

class Logger(irclib.SimpleIRCClient):
	
	def __init__(self, server, port, channel, nick, password, username,
				ircname, topic, localaddress, localport, ssl, ipv6,
				mysql_server, mysql_port, mysql_database,
				mysql_user, mysql_password, webdav_settings):

		irclib.SimpleIRCClient.__init__(self)
		
		#IRC details
		self.server = server
		self.port = port
		self.target = channel
		self.channel = channel
		self.nick = nick
		self.password = password
		self.username = username
		self.ircname = ircname
		self.topic = topic
		self.localaddress = localaddress
		self.localport = localport
		self.ssl = ssl
		self.ipv6 = ipv6
		
		#MySQL details
		self.mysql_server = mysql_server
		self.mysql_port = mysql_port
		self.mysql_database = mysql_database
		self.mysql_user = mysql_user
		self.mysql_password = mysql_password

		#webdav
		self.webdav = easywebdav.connect(webdav_settings['host'],
			port=int(webdav_settings.get('port', 0)),
			username=webdav_settings['username'],
			password=webdav_settings['password'],
			protocol=webdav_settings['protocol'],
			verify_ssl=bool(webdav_settings.get('verify_ssl', 'True') in [ 'True' ])
			)
		self.webdav_download_dir = webdav_settings.get('download_dir', '.')

		#Regexes
		self.nick_reg = re.compile("^" + nick + "[:,]\s*(.*)")

		#Message Cache
		self.message_cache = []		#messages are stored here before getting pushed to the db
		
		#Disconnect Countdown
		self.disconnect_countdown = 5
	
		self.last_ping = 0
		self.ircobj.delayed_commands.append( (time.time()+5, self._no_ping, [] ) )

		self.connect(self.server, self.port, self.nick, self.password, self.username, self.ircname, self.localaddress, self.localport, self.ssl, self.ipv6)
	
	def _no_ping(self):
		if self.last_ping >= 1200:
			raise irclib.ServerNotConnectedError
		else:
			self.last_ping += 10
		self.ircobj.delayed_commands.append( (time.time()+10, self._no_ping, [] ) )


	def _dispatcher(self, c, e):
	# This determines how a new event is handled. 
		if(e.eventtype() == "topic" or 
		   e.eventtype() == "part" or
		   e.eventtype() == "join" or
		   e.eventtype() == "action" or
		   e.eventtype() == "quit" or
		   e.eventtype() == "nick" or
		   e.eventtype() == "pubmsg"):
			try:
				source = e.source().split("!")[0]

				channel = self.channel[1:]

			except IndexError:
				source = ""
			try:
				if e.eventtype() == "nick":
					text = e.target()
				else:
					text = e.arguments()[0]
			except IndexError:
				text = ""
		
			# Print message to stdout
			print str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")) + " ("+ e.eventtype() +") [#" + channel + "] <" + source + "> " + text 
		
			# Prepare a message for the buffer
			message_dict = {"channel":channel,
							"name": source,
							"message": text,
							"type": e.eventtype(),
							"time": str(datetime.datetime.utcnow()) } 
			
			# Most of the events are pushed to the buffer. 
			self.message_cache.append( message_dict )
		
		m = "on_" + e.eventtype()	
		if hasattr(self, m):
			getattr(self, m)(c, e)

	def on_nicknameinuse(self, c, e):
		c.nick(c.get_nickname() + "_")

	def on_welcome(self, connection, event):
		if irclib.is_channel(self.target):
			connection.join(self.target)

	def on_join(self, connection, event):
		# only change topic if it is the bot joining
		try:
			source = event.source().split("!")[0]
			if source != self.nick:
				return
		except IndexError:
			return
		if self.topic and irclib.is_channel(self.target):
			connection.topic(self.target, self.topic)

	def on_disconnect(self, connection, event):
		self.on_ping(connection, event)
		connection.disconnect()
		raise irclib.ServerNotConnectedError

	def on_ping(self, connection, event):
		self.last_ping = 0
		try:
			db = pierc_db.Pierc_DB( self.mysql_server,
												 			self.mysql_port,
												 			self.mysql_database, 
											   	 			self.mysql_user,
															self.mysql_password)
			for message in self.message_cache:
				db.insert_line(message["channel"], message["name"], message["time"], message["message"], message["type"] )

			db.commit()
			if self.disconnect_countdown < 10:
				self.disconnect_countdown = self.disconnect_countdown + 1
			
			del db
			# clear the cache
			self.message_cache = []	
				
		except Exception, e:
			print "Database Commit Failed! Let's wait a bit!" 
			print e
			if self.disconnect_countdown <= 0:
				sys.exit( 0 )
			if self.disconnect_countdown <= 3:
				connection.privmsg(self.channel, "Database connection lost! " + str(self.disconnect_countdown) + " retries until I give up entirely!" )
			self.disconnect_countdown = self.disconnect_countdown - 1

	def on_pubmsg(self, connection, event):
		text = event.arguments()[0]

		# If you talk to the bot, this is how he responds.
		match = self.nick_reg.match(text)
		if not match:
			return

		match = match.group(1)

		if match == "ping":
			connection.privmsg(self.channel, "pong")
			self.on_ping(connection, event)

		if match == "check incoming":
			connection.privmsg(self.channel, "checking for incoming debian packages...")
			try:
				files = self.webdav.ls('/debian')
				if len(files) == 1:
					connection.privmsg(self.channel, "No files to download.")
					return
				changes_files = []
				for f in files:
					if f.contenttype == 'httpd/unix-directory':
						continue
					connection.privmsg(self.channel, "downloading " + f.name)
					local_file = f.name.replace('/debian', self.webdav_download_dir)
					if local_file[-8:] == '.changes':
						changes_files.append(local_file)
					self.webdav.download(f.name, local_file)
					self.webdav.delete(f.name)
				if len(changes_files) == 0:
					connection.privmsg(self.channel, "No .changes files found.")
					return
				for f in changes_files:
					connection.privmsg(self.channel, "submitting " + f.split('/')[-1])
					subprocess.check_call(['dput', 'ev3dev.org', f])
				connection.privmsg(self.channel, "Done! You should receive an email soon.")
			except Exception, e:
				connection.privmsg(self.channel, e)

		else:
			connection.privmsg(self.channel, "I don't know what that means.")

def main():
	mysql_settings = config.config("mysql_config.txt")
	irc_settings = config.config("irc_config.txt")
	webdav_settings = config.config("webdav_config.txt")
	c = Logger(
				irc_settings["server"], 
				int(irc_settings["port"]), 
				irc_settings["channel"],
				irc_settings["nick"],
				irc_settings.get("password",None),
				irc_settings.get("username",None),
				irc_settings.get("ircname",None),
				irc_settings.get("topic",None),
				irc_settings.get("localaddress",""),
				int(irc_settings.get("localport",0)),
				bool(irc_settings.get("ssl",False)),
				bool(irc_settings.get("ipv6",False)), 

				mysql_settings["server"],
				int(mysql_settings["port"]),
				mysql_settings["database"],
				mysql_settings["user"],
				mysql_settings["password"],

				webdav_settings
				)
	c.start()

if __name__ == "__main__":
	irc_settings = config.config("irc_config.txt")
	reconnect_interval = irc_settings["reconnect"]
	while True:
		try:
			main()
		except irclib.ServerNotConnectedError:
			print "Server Not Connected! Let's try again!"
			time.sleep(float(reconnect_interval))
