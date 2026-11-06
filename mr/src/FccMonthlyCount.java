package org.example;

import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Job;
import org.apache.hadoop.mapreduce.Mapper;
import org.apache.hadoop.mapreduce.Reducer;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;

import java.io.IOException;
import java.io.StringReader;

public class FccMonthlyCount {

    public static class FccMonthMapper
            extends Mapper<LongWritable, Text, Text, LongWritable> {

        private final Text outKey = new Text();
        private final LongWritable outValue = new LongWritable(1);

        @Override
        protected void map(LongWritable key, Text value, Context context)
                throws IOException, InterruptedException {
            String line = value.toString();

            // 跳过表头
            if (line.startsWith("Ticket ID,")) {
                return;
            }

            try (CSVParser parser = CSVParser.parse(new StringReader(line), CSVFormat.DEFAULT)) {
                for (CSVRecord record : parser) {
                    if (record.size() < 3) {
                        context.getCounter("FccMonthly", "INVALID_CSV").increment(1);
                        return;
                    }

                    // 第2列 Date Created，格式：MM/dd/yyyy
                    String dateStr = record.get(2).trim();
                    if (dateStr.isEmpty()) {
                        context.getCounter("FccMonthly", "EMPTY_DATE").increment(1);
                        return;
                    }

                    // 字符串拆分拼接年月，避开日期解析异常
                    String[] parts = dateStr.split("/");
                    if (parts.length != 3) {
                        context.getCounter("FccMonthly", "BAD_DATE_FORMAT").increment(1);
                        return;
                    }
                    String month = parts[2] + "-" + parts[0]; // 年-月

                    outKey.set(month);
                    context.write(outKey, outValue);
                }
            } catch (Exception e) {
                context.getCounter("FccMonthly", "PARSE_ERROR").increment(1);
            }
        }
    }

    public static class FccMonthReducer
            extends Reducer<Text, LongWritable, Text, LongWritable> {
        private final LongWritable result = new LongWritable();
        @Override
        protected void reduce(Text key, Iterable<LongWritable> values, Context context)
                throws IOException, InterruptedException {
            long sum = 0;
            for (LongWritable v : values) sum += v.get();
            result.set(sum);
            context.write(key, result);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("用法：FccMonthlyCount <输入路径> <输出路径>");
            System.exit(2);
        }
        Configuration conf = new Configuration();
        Job job = Job.getInstance(conf, "FCC Monthly Complaint Count");
        job.setJarByClass(FccMonthlyCount.class);

        job.setMapperClass(FccMonthMapper.class);
        job.setCombinerClass(FccMonthReducer.class);
        job.setReducerClass(FccMonthReducer.class);

        job.setMapOutputKeyClass(Text.class);
        job.setMapOutputValueClass(LongWritable.class);
        job.setOutputKeyClass(Text.class);
        job.setOutputValueClass(LongWritable.class);
        job.setNumReduceTasks(1);

        FileInputFormat.addInputPath(job, new Path(args[0]));
        FileOutputFormat.setOutputPath(job, new Path(args[1]));
        System.exit(job.waitForCompletion(true) ? 0 : 1);
    }
}
