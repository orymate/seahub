import datetime
import os
import re
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import datetime_safe

from seaserv import get_group_members

from shortcuts import get_first_object_or_none
from notifications.models import UserNotification
from profile.models import Profile

class GroupMessage(models.Model):
    group_id = models.IntegerField(db_index=True)
    from_email = models.EmailField()
    message = models.CharField(max_length=500)
    timestamp = models.DateTimeField(default=datetime.datetime.now)

    def reprJSON(self):
        DATE_FORMAT = "%Y-%m-%d"
        TIME_FORMAT = "%H:%M:%S"
        d = datetime_safe.new_datetime(self.timestamp)
        timestamp = d.strftime("%s %s" % (DATE_FORMAT, TIME_FORMAT))
        return dict(group_id=self.group_id, from_email=self.from_email,
                    message=self.message, timestamp=timestamp)

class MessageReply(models.Model):
    reply_to = models.ForeignKey(GroupMessage)
    from_email = models.EmailField()
    message = models.CharField(max_length=150)
    timestamp = models.DateTimeField(default=datetime.datetime.now)

    def reprJSON(self):
        DATE_FORMAT = "%Y-%m-%d"
        TIME_FORMAT = "%H:%M:%S"
        d = datetime_safe.new_datetime(self.timestamp)
        timestamp = d.strftime("%s %s" % (DATE_FORMAT, TIME_FORMAT))
        return dict(reply_to=self.reply_to_id, from_email=self.from_email,
                    message=self.message, timestamp=timestamp)

class MessageAttachment(models.Model):
    """
    Model used to represents a message attachment related to a group message.
    """
    group_message = models.ForeignKey(GroupMessage)
    repo_id = models.CharField(max_length=40)
    attach_type = models.CharField(max_length=5) # `file` or `dir`
    path = models.TextField()
    src = models.CharField(max_length=20) # `recommend` or `filecomment`

@receiver(post_save, sender=MessageReply)
def msgreply_save_handler(sender, instance, **kwargs):
    """
    Handle sending notification to '@<user>' when reply messages.
    """
    from_email = instance.from_email
    reply_msg =  instance.message
    group_msg =  instance.reply_to
    to_user = ''

    from base.templatetags.seahub_tags import at_pattern
    m = re.match(at_pattern, reply_msg)
    if m:
        nickname_or_emailprefix = m.group()[1:]
        for member in get_group_members(group_msg.group_id):
            # For every group member, get his username and nickname if
            # it exists, check whether match.
            username = member.user_name
            if username == from_email:
                continue
            
            p = get_first_object_or_none(
                Profile.objects.filter(user=username))
            nickname = p.nickname if p else ''
            if nickname == nickname_or_emailprefix or \
                    username.split('@')[0] == nickname_or_emailprefix:
                to_user = username
                break

        if to_user:
            # Send notification to the user if he replies someone else'
            # message.
            try:
                UserNotification.objects.get(to_user=to_user,
                                             msg_type='grpmsg_reply',
                                             detail=group_msg.id)
            except UserNotification.DoesNotExist:
                n = UserNotification(to_user=to_user,
                                     msg_type='grpmsg_reply',
                                     detail=group_msg.id)
                n.save()

class GroupWikiManager(models.Manager):
    def save_group_wiki(self, group_id, repo_id):
        """
        Create or update group wiki.
        """
        try:
            groupwiki = self.get(group_id=group_id)
            groupwiki.repo_id = repo_id
        except self.model.DoesNotExist:
            groupwiki = self.model(group_id=group_id, repo_id=repo_id)
        groupwiki.save(using=self._db)
        return groupwiki

class GroupWiki(models.Model):
    group_id = models.IntegerField()
    repo_id = models.CharField(max_length=36)
    objects = GroupWikiManager()

    class Meta:
        unique_together = ('group_id', 'repo_id')


class PublicGroup(models.Model):
    """
    To record a public group
    """
    group_id = models.IntegerField(db_index=True)
