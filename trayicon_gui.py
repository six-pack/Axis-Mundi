import wx
from utilities import resource_path

TRAY_TOOLTIP = 'Axis Mundi'
TRAY_ICON = 'icon.png'


def create_menu_item(menu, label, func):
    item = wx.MenuItem(menu, -1, label)
    menu.Bind(wx.EVT_MENU, func, id=item.GetId())
    menu.AppendItem(item)
    return item


class TaskBarIcon(wx.TaskBarIcon):

    def __init__(self):
        super(TaskBarIcon, self).__init__()
        self.set_icon(resource_path(TRAY_ICON))
        self.Bind(wx.EVT_TASKBAR_LEFT_DOWN, self.on_left_down)

    def CreatePopupMenu(self):
        menu = wx.Menu('Axis Mundi')
        # create_menu_item(menu, 'Restart', self.on_restart) # TODO: implement
        # restart function
        create_menu_item(menu, 'Shutdown', self.on_exit)
        return menu

    def set_icon(self, path):
        icon = wx.IconFromBitmap(wx.Bitmap(path))
        self.SetIcon(icon, TRAY_TOOLTIP)

    def on_left_down(self, event):
        wx.MessageBox('Test', 'Indo', wx.OK)
        menu = self.CreatePopupMenu()
        self.PopupMenu(menu)
        menu.Destroy()

    def on_restart(self, event):
        print 'Restart request from status GUI'

    def on_exit(self, event):
        print "Shutdown from gui"
        wx.CallAfter(self.Destroy)
        wx.GetApp().Exit()
#        wx.GetApp().ExitMainLoop()
