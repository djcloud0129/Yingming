using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

internal static class YingmingPetLauncher
{
    [STAThread]
    private static int Main()
    {
        string baseDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location) ?? AppDomain.CurrentDomain.BaseDirectory;
        string appDir = Path.Combine(baseDir, "app");
        string pythonw = Path.Combine(baseDir, "runtime", "python", "pythonw.exe");
        string python = Path.Combine(baseDir, "runtime", "python", "python.exe");
        string script = Path.Combine(appDir, "yingming_pet.pyw");

        string executable = File.Exists(pythonw) ? pythonw : python;
        if (!File.Exists(executable))
        {
            MessageBox.Show("Python runtime was not found in this bundle.", "Yingming failed to start", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }

        if (!File.Exists(script))
        {
            MessageBox.Show("Yingming pet entry file was not found.", "Yingming failed to start", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }

        try
        {
            ProcessStartInfo info = new ProcessStartInfo
            {
                FileName = executable,
                Arguments = Quote(script),
                WorkingDirectory = appDir,
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            info.EnvironmentVariables["YINGMING_BUNDLE_DIR"] = baseDir;
            Process.Start(info);
            return 0;
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, "Yingming failed to start", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }
}
